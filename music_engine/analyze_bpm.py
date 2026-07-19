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


def detect_beats(file_path: str) -> BeatInfo:
    # 22050Hzへダウンサンプルしてメモリを節約する変更を試したが、実際の曲でBPM・
    # ビート位置が大きくずれる不具合が発生したため revert 済み。デスクトップ版
    # （music_edit_app、こちらは無変更）と同じ sr=None（ネイティブレート）に戻し、
    # メモリ対策はVM側のスペック（メモリ増強）で行う方針にした。
    y, sr = librosa.load(file_path, sr=None)
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
