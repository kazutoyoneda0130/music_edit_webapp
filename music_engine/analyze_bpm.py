"""
音源ファイル（mp3, m4aなど）からBPM・イントロ／アウトロ・N×8ブロックを算出するスクリプト。

最初にビートが検知されたタイミングまでを「イントロ」、
最後にビートが検知されたタイミング以降を「アウトロ」とし、
その間を指定したエイト数（デフォルト4×8＝32ビート）単位で区切り、
各ブロックの開始～終了時刻（mm:ss）とあわせて出力する。

使い方:
    python analyze_bpm.py <音源ファイルのパス> [--unit 1|2|4|8...]
"""

import argparse
import sys
import warnings
from dataclasses import dataclass, field

import librosa
import numpy as np

# m4aなどlibsndfileが直接扱えない形式はaudioreadにフォールバックする際に
# 非推奨警告・UserWarningが出るが、正常な読み込み経路なので抑制する。
warnings.filterwarnings("ignore", message="PySoundFile failed", category=UserWarning)
warnings.filterwarnings("ignore", message="librosa.core.audio.__audioread_load", category=FutureWarning)

DEFAULT_EIGHTS_PER_BLOCK = 4

# 複数曲を繋げた「最終版音源」（他アプリで編集済みのもの含む）を1曲固定のBPM前提で
# 解析すると全体で1つの平均BPMに丸められてしまうため、区間ごとにBPMが変わる前提で
# 曲の境目を検出する（detect_multi_tempo_segments）。境目候補は、
# librosa.feature.tempo(aggregate=None)が返すフレームごとのローカルBPM曲線
# （内部でac_size秒の自己相関窓を使っており、単発の打点ノイズに強い）を、
# 各点の前後TEMPO_WINDOW_SEC秒ずつの平均で比較し、大きく変化した点とする。
TEMPO_WINDOW_SEC = 6.0
MIN_SEGMENT_SEC = 15.0
CHANGE_THRESHOLD = 0.12
BOUNDARY_BIAS_CORRECTION_SEC = 4.0


@dataclass
class Block:
    eights: float
    start_sec: float
    end_sec: float


@dataclass
class AnalysisResult:
    bpm: float
    duration: float
    intro_sec: float
    outro_sec: float
    blocks: list[Block]


@dataclass
class Segment:
    """複数曲を繋げた音源のうち、1つの曲相当とみなされた区間（絶対秒）。"""

    bpm: float
    start_sec: float
    end_sec: float
    blocks: list[Block]


@dataclass
class MultiTempoResult:
    duration: float
    segments: list[Segment]


@dataclass
class BeatInfo:
    """librosaによるビート検出結果（重い処理）。ブロック単位を変えても再計算不要。

    beat_timesは検出された全ビートの時刻（秒）。ブロック境界はこの実測値を直接使い、
    平均BPMからの秒数計算だけに頼らないことで、曲後半でのズレを防ぐ。
    """

    bpm: float
    duration: float
    first_beat: float
    last_beat: float
    beat_times: list[float] = field(default_factory=list)


def format_time(sec: float) -> str:
    sec = max(0.0, sec)
    minutes = int(sec // 60)
    seconds = int(sec % 60)
    return f"{minutes:02d}:{seconds:02d}"


def detect_beats_from_signal(y: np.ndarray, sr: int) -> BeatInfo:
    """すでにロード済みの信号(y, sr)からビートを検出する（detect_beatsの中身を
    切り出したもの。detect_multi_tempo_segmentsが区間ごとの音声スライスに
    対して同じロジックを使い回すために分離している。挙動はdetect_beatsと同一）。
    """
    duration = librosa.get_duration(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.asarray(tempo).item())

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    if len(beat_times) == 0:
        raise ValueError("ビートを検出できませんでした")

    return BeatInfo(
        bpm=bpm,
        duration=duration,
        first_beat=float(beat_times[0]),
        last_beat=float(beat_times[-1]),
        beat_times=[float(t) for t in beat_times],
    )


def detect_beats(file_path: str) -> BeatInfo:
    # 22050Hzへダウンサンプルしてメモリを節約する変更を試したが、実際の曲でBPM・
    # ビート位置が大きくずれる不具合が発生したため revert 済み。デスクトップ版
    # （music_edit_app、こちらは無変更）と同じ sr=None（ネイティブレート）に戻し、
    # メモリ対策はVM側のスペック（メモリ増強）で行う方針にした。
    y, sr = librosa.load(file_path, sr=None)
    return detect_beats_from_signal(y, sr)


def _detect_tempo_change_boundaries(y: np.ndarray, sr: int, duration: float) -> list[float]:
    """ローカルBPM曲線の急激な変化点を曲の境目候補として検出し、
    0秒・duration秒を含む昇順の境界秒リストを返す。
    """
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_curve = librosa.feature.tempo(onset_envelope=onset_env, sr=sr, aggregate=None)
    hop_length = 512
    frame_times = librosa.frames_to_time(np.arange(len(tempo_curve)), sr=sr, hop_length=hop_length)

    frame_rate = sr / hop_length
    window = max(1, round(TEMPO_WINDOW_SEC * frame_rate))

    boundaries = [0.0]
    last_boundary = 0.0
    for i in range(window, len(tempo_curve) - window):
        before = tempo_curve[i - window:i]
        after = tempo_curve[i:i + window]
        avg_before = float(np.mean(before))
        avg_after = float(np.mean(after))
        if avg_before <= 0:
            continue
        change = abs(avg_after - avg_before) / avg_before
        # librosa.feature.tempo(aggregate=None)はac_size秒(既定8秒)の自己相関窓を
        # 使っているため、実際の境目より手前で変化が検出される系統的なラグが生じる。
        # 経験的にほぼac_size/2秒分前倒しになるため、その分を補正して実際の境目に近づける。
        t = float(frame_times[i]) + BOUNDARY_BIAS_CORRECTION_SEC
        if change > CHANGE_THRESHOLD and t - last_boundary > MIN_SEGMENT_SEC:
            boundaries.append(t)
            last_boundary = t
    boundaries.append(duration)
    return boundaries


def detect_multi_tempo_segments(file_path: str, eights_per_block: int = DEFAULT_EIGHTS_PER_BLOCK) -> MultiTempoResult:
    """複数曲を繋げた「最終版音源」を、曲ごとにBPMが変わる前提で区間に分割し、
    区間ごとに個別のBPM/ブロックを検出する。各区間は独立した音声スライスとして
    detect_beats_from_signal + build_blocks にかけ、結果のstart_sec/end_secを
    区間の絶対秒に戻す（build_blocks自体は1曲分析と全く同じロジックのまま）。
    """
    y, sr = librosa.load(file_path, sr=None)
    duration = librosa.get_duration(y=y, sr=sr)
    boundaries = _detect_tempo_change_boundaries(y, sr, duration)

    segments: list[Segment] = []
    for seg_start, seg_end in zip(boundaries[:-1], boundaries[1:]):
        y_seg = y[int(seg_start * sr):int(seg_end * sr)]
        try:
            seg_beat_info = detect_beats_from_signal(y_seg, sr)
        except ValueError:
            # 無音に近い等、ビートを検出できない区間は等間隔の1ブロック扱いにする
            fallback_bpm = 120.0
            eights = max(1, round((seg_end - seg_start) / ((60 / fallback_bpm) * 8)))
            segments.append(Segment(
                bpm=fallback_bpm, start_sec=seg_start, end_sec=seg_end,
                blocks=[Block(eights=eights, start_sec=seg_start, end_sec=seg_end)],
            ))
            continue

        seg_result = build_blocks(seg_beat_info, eights_per_block)
        blocks = [
            Block(eights=b.eights, start_sec=b.start_sec + seg_start, end_sec=b.end_sec + seg_start)
            for b in seg_result.blocks
        ]
        segments.append(Segment(bpm=seg_beat_info.bpm, start_sec=seg_start, end_sec=seg_end, blocks=blocks))

    return MultiTempoResult(duration=duration, segments=segments)


def build_blocks(beat_info: BeatInfo, eights_per_block: int = DEFAULT_EIGHTS_PER_BLOCK) -> AnalysisResult:
    beat_times = beat_info.beat_times
    first_beat = beat_info.first_beat
    last_beat = beat_info.last_beat
    intro_sec = first_beat
    outro_sec = beat_info.duration - last_beat

    # ブロック境界は実測したビート時刻をそのまま使う（平均BPMからの秒数計算だと、
    # テンポにわずかな揺れがある曲で後半になるほど実際のビートとズレていくため）。
    beats_per_block = eights_per_block * 8
    total_intervals = len(beat_times) - 1  # ビートN個の間にはN-1個の「間隔（1拍）」がある
    full_blocks = total_intervals // beats_per_block
    remainder_beats = total_intervals - full_blocks * beats_per_block
    remainder_eights = remainder_beats / 8

    blocks: list[Block] = []
    for i in range(full_blocks):
        start_idx = i * beats_per_block
        end_idx = start_idx + beats_per_block
        blocks.append(Block(eights=eights_per_block, start_sec=beat_times[start_idx], end_sec=beat_times[end_idx]))
    if remainder_eights >= 0.5:
        start_idx = full_blocks * beats_per_block
        blocks.append(Block(eights=round(remainder_eights), start_sec=beat_times[start_idx], end_sec=last_beat))

    return AnalysisResult(
        bpm=beat_info.bpm,
        duration=beat_info.duration,
        intro_sec=intro_sec,
        outro_sec=outro_sec,
        blocks=blocks,
    )


def analyze(file_path: str, eights_per_block: int = DEFAULT_EIGHTS_PER_BLOCK) -> AnalysisResult:
    beat_info = detect_beats(file_path)
    return build_blocks(beat_info, eights_per_block)


def main() -> None:
    parser = argparse.ArgumentParser(description="音源ファイル（mp3, m4aなど）のBPM・イントロ／アウトロ・N×8ブロックを算出します")
    parser.add_argument("file_path", help="解析する音源ファイルのパス（mp3, m4aなど）")
    parser.add_argument(
        "-u", "--unit", type=int, default=DEFAULT_EIGHTS_PER_BLOCK,
        help=f"1ブロックあたりのエイト数（デフォルト{DEFAULT_EIGHTS_PER_BLOCK} = {DEFAULT_EIGHTS_PER_BLOCK}×8）",
    )
    args = parser.parse_args()

    try:
        result = analyze(args.file_path, eights_per_block=args.unit)
    except FileNotFoundError:
        print(f"ファイルが見つかりません: {args.file_path}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"BPM: {result.bpm:.2f}")
    print(f"・イントロ {result.intro_sec:.0f}秒")
    for block in result.blocks:
        # 表示上、ブロックの終了秒は次のブロックの開始秒と重複しないよう1秒引く
        end_display = max(block.start_sec, block.end_sec - 1)
        print(f"・{block.eights:g}×8({format_time(block.start_sec)}~{format_time(end_display)})")
    print(f"・アウトロ {result.outro_sec:.0f}秒")


if __name__ == "__main__":
    main()
