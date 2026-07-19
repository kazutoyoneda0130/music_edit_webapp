"""
複数の音源ファイル（mp3など）を連結し、1つのmp3として出力するスクリプト。

2つのモードをサポート:
  モードA（BPM調整あり）: 最初のファイルのBPMに合わせて後続ファイルをタイムストレッチしてからクロスフェードで連結
  モードB（BPM調整なし）: BPMはそのままクロスフェードのみで連結

使い方:
    python concat_audio.py -m a file1.mp3 file2.mp3 file3.mp3 -o combined.mp3
    python concat_audio.py -m b file1.mp3 file2.mp3 --crossfade 3 -o combined.mp3
"""

import argparse
import sys
import warnings
from pathlib import Path

import librosa
import numpy as np
from pydub import AudioSegment

from music_engine.analyze_bpm import detect_beats

# m4aなどlibsndfileが直接扱えない形式はaudioreadにフォールバックする際に
# 非推奨警告・UserWarningが出るが、正常な読み込み経路なので抑制する。
warnings.filterwarnings("ignore", message="PySoundFile failed", category=UserWarning)
warnings.filterwarnings("ignore", message="librosa.core.audio.__audioread_load", category=FutureWarning)

DEFAULT_CROSSFADE_SEC = 2.0

FADE_PATTERNS = ["linear", "equal_power", "scurve"]
FADE_PATTERN_LABELS = {
    "linear": "線形",
    "equal_power": "イコールパワー",
    "scurve": "Sカーブ",
}
DEFAULT_FADE_PATTERN = "equal_power"

_SAMPLE_WIDTH_DTYPE = {1: np.int8, 2: np.int16, 4: np.int32}


def detect_bpm(file_path: str) -> float:
    return detect_beats(file_path).bpm


def numpy_to_audiosegment(y: np.ndarray, sr: int) -> AudioSegment:
    y = np.clip(y, -1.0, 1.0)
    if y.ndim == 1:
        channels = 1
        interleaved = y
    else:
        channels = y.shape[0]
        interleaved = y.T.flatten()  # (channels, samples) -> インターリーブ (LRLR...)
    pcm16 = (interleaved * 32767).astype(np.int16)
    return AudioSegment(pcm16.tobytes(), frame_rate=sr, sample_width=2, channels=channels)


def time_stretch_to_bpm(file_path: str, source_bpm: float, target_bpm: float) -> AudioSegment:
    y, sr = librosa.load(file_path, sr=None, mono=False)
    rate = target_bpm / source_bpm
    if y.ndim == 1:
        stretched = librosa.effects.time_stretch(y, rate=rate)
    else:
        stretched = np.stack([librosa.effects.time_stretch(channel, rate=rate) for channel in y])
    return numpy_to_audiosegment(stretched, sr)


def load_segment(file_path: str) -> AudioSegment:
    return AudioSegment.from_file(file_path)


def time_stretch_segment(segment: AudioSegment, source_bpm: float, target_bpm: float) -> AudioSegment:
    """既に組み立て済みのAudioSegmentを、BPM比に応じてタイムストレッチする（ピッチは維持）"""
    if source_bpm <= 0 or target_bpm <= 0 or source_bpm == target_bpm:
        return segment

    arr = _segment_to_float_array(segment).astype(np.float32)
    rate = target_bpm / source_bpm
    if arr.ndim == 1:
        stretched = librosa.effects.time_stretch(arr, rate=rate)
    else:
        stretched = np.stack(
            [librosa.effects.time_stretch(arr[:, ch], rate=rate) for ch in range(arr.shape[1])], axis=1
        )
    return _float_array_to_segment(stretched, segment.frame_rate, segment.sample_width, segment.channels)


def _segment_to_float_array(seg: AudioSegment) -> np.ndarray:
    samples = np.array(seg.get_array_of_samples()).astype(np.float64)
    if seg.channels > 1:
        samples = samples.reshape(-1, seg.channels)
    max_val = float(2 ** (8 * seg.sample_width - 1))
    return samples / max_val


def _float_array_to_segment(arr: np.ndarray, frame_rate: int, sample_width: int, channels: int) -> AudioSegment:
    dtype = _SAMPLE_WIDTH_DTYPE.get(sample_width, np.int16)
    max_val = float(2 ** (8 * sample_width - 1) - 1)
    clipped = np.clip(arr, -1.0, 1.0)
    ints = (clipped * max_val).astype(dtype)
    if channels > 1:
        ints = ints.reshape(-1)
    return AudioSegment(ints.tobytes(), frame_rate=frame_rate, sample_width=sample_width, channels=channels)


def _fade_curve(t: np.ndarray, pattern: str) -> np.ndarray:
    """t: 0→1（フェードイン方向の進行度）に対するゲイン(0→1)を返す"""
    if pattern == "linear":
        return t
    if pattern == "equal_power":
        # 一定パワー（音量の落ち込みを感じにくい）クロスフェード
        return np.sin(t * np.pi / 2)
    if pattern == "scurve":
        # なめらかなS字カーブ（smoothstep）
        return t * t * (3 - 2 * t)
    raise ValueError(f"不明なフェードパターン: {pattern}")


def crossfade_segments(
    seg1: AudioSegment, seg2: AudioSegment, crossfade_ms: int, pattern: str = DEFAULT_FADE_PATTERN
) -> AudioSegment:
    """seg1の末尾とseg2の先頭を、指定パターン・長さでクロスフェードしながら連結する"""
    if crossfade_ms <= 0:
        return seg1 + seg2

    max_crossfade = max(0, min(len(seg1), len(seg2)) - 1)
    cf = max(0, min(crossfade_ms, max_crossfade))
    if cf <= 0:
        return seg1 + seg2

    seg2 = seg2.set_frame_rate(seg1.frame_rate).set_channels(seg1.channels).set_sample_width(seg1.sample_width)

    head = seg1[:-cf]
    tail1 = seg1[-cf:]
    overlap2 = seg2[:cf]
    rest2 = seg2[cf:]

    tail1_arr = _segment_to_float_array(tail1)
    overlap2_arr = _segment_to_float_array(overlap2)
    n = min(len(tail1_arr), len(overlap2_arr))
    tail1_arr = tail1_arr[:n]
    overlap2_arr = overlap2_arr[:n]

    t = np.linspace(0.0, 1.0, n, endpoint=False) if n > 0 else np.array([])
    fade_in_curve = _fade_curve(t, pattern)
    fade_out_curve = _fade_curve(1.0 - t, pattern)
    if seg1.channels > 1:
        fade_in_curve = fade_in_curve[:, None]
        fade_out_curve = fade_out_curve[:, None]

    mixed = tail1_arr * fade_out_curve + overlap2_arr * fade_in_curve
    mixed_seg = _float_array_to_segment(mixed, seg1.frame_rate, seg1.sample_width, seg1.channels)

    return head + mixed_seg + rest2


def concat_with_crossfade(
    segments: list[AudioSegment], crossfade_ms: int, pattern: str = DEFAULT_FADE_PATTERN
) -> AudioSegment:
    if not segments:
        raise ValueError("連結する音源がありません")

    combined = segments[0]
    for seg in segments[1:]:
        combined = crossfade_segments(combined, seg, crossfade_ms, pattern)
    return combined


def concat_mode_a(
    file_paths: list[str], crossfade_sec: float = DEFAULT_CROSSFADE_SEC, fade_pattern: str = DEFAULT_FADE_PATTERN
) -> AudioSegment:
    """最初のファイルのBPMに合わせて後続ファイルをタイムストレッチしてからクロスフェード連結する"""
    if len(file_paths) < 2:
        raise ValueError("2つ以上のファイルを指定してください")

    reference_bpm = detect_bpm(file_paths[0])
    segments = [load_segment(file_paths[0])]
    for path in file_paths[1:]:
        bpm = detect_bpm(path)
        segments.append(time_stretch_to_bpm(path, bpm, reference_bpm))

    crossfade_ms = int(round(crossfade_sec * 1000))
    return concat_with_crossfade(segments, crossfade_ms, fade_pattern)


def concat_mode_b(
    file_paths: list[str], crossfade_sec: float = DEFAULT_CROSSFADE_SEC, fade_pattern: str = DEFAULT_FADE_PATTERN
) -> AudioSegment:
    """BPMはそのままクロスフェードのみで連結する"""
    if len(file_paths) < 2:
        raise ValueError("2つ以上のファイルを指定してください")

    segments = [load_segment(p) for p in file_paths]
    crossfade_ms = int(round(crossfade_sec * 1000))
    return concat_with_crossfade(segments, crossfade_ms, fade_pattern)


def concat_files(
    file_paths: list[str],
    mode: str,
    crossfade_sec: float = DEFAULT_CROSSFADE_SEC,
    fade_pattern: str = DEFAULT_FADE_PATTERN,
) -> AudioSegment:
    if mode == "a":
        return concat_mode_a(file_paths, crossfade_sec, fade_pattern)
    if mode == "b":
        return concat_mode_b(file_paths, crossfade_sec, fade_pattern)
    raise ValueError(f"不明なモード: {mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="複数の音源ファイルを連結して1つのmp3として出力します")
    parser.add_argument("files", nargs="+", help="連結する音源ファイル（2つ以上、指定した順序で連結）")
    parser.add_argument(
        "-m", "--mode", choices=["a", "b"], required=True,
        help="a: BPM調整あり（最初のファイルのBPMに他をタイムストレッチで合わせる）／ b: BPM調整なし",
    )
    parser.add_argument(
        "-c", "--crossfade", type=float, default=DEFAULT_CROSSFADE_SEC,
        help=f"クロスフェード長（秒、デフォルト{DEFAULT_CROSSFADE_SEC}秒）",
    )
    parser.add_argument(
        "-p", "--fade-pattern", choices=FADE_PATTERNS, default=DEFAULT_FADE_PATTERN,
        help=f"クロスフェードのパターン（デフォルト{DEFAULT_FADE_PATTERN}）",
    )
    parser.add_argument("-o", "--output", default="combined.mp3", help="出力ファイルパス（デフォルト combined.mp3）")
    args = parser.parse_args()

    if len(args.files) < 2:
        print("2つ以上のファイルを指定してください", file=sys.stderr)
        sys.exit(1)

    try:
        combined = concat_files(args.files, args.mode, args.crossfade, args.fade_pattern)
    except (FileNotFoundError, ValueError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output)
    combined.export(out_path, format="mp3")
    print(f"書き出しました: {out_path} ({len(combined) / 1000:.1f}秒)")


if __name__ == "__main__":
    main()
