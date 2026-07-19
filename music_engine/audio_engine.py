"""
複数曲の並び替え・スキップ後の音源を作り、指定した接続部（junction）設定で
クロスフェード結合するための、UIに依存しない純粋関数群。

music_edit_app/gui_app.py（PySide6デスクトップアプリ）内のロジック
（モジュールレベル関数 + MainWindowインスタンスメソッドに埋まっていた
 接続部のエイト数→秒数換算・タイムライン計算）を、明示的な引数を取る
純粋関数として書き起こしたもの。

重要: 「曲スロットが空いている場合、接続部の基準BPM・クロスフェード長は
junction_index番目とjunction_index+1番目の『固定スロット位置』を見る」
という、デスクトップ版の挙動をそのまま踏襲している（実際に結合される
曲同士とズレることがあるが、意図的にそうしている）。
"""

from dataclasses import dataclass, field

from pydub import AudioSegment

from music_engine.analyze_bpm import AnalysisResult
from music_engine.concat_audio import (
    DEFAULT_FADE_PATTERN,
    concat_with_crossfade,
    time_stretch_segment,
)

EXPORT_FORMAT_MAP = {".mp3": "mp3", ".m4a": "ipod", ".wav": "wav"}
UNIT_OPTIONS = [1, 2, 4, 8]
DEFAULT_UNIT = 4
DEFAULT_FADE_EIGHTS = 1.0


def sec_to_ms(sec: float) -> int:
    return int(round(sec * 1000))


@dataclass
class TimelineEntry:
    kind: str  # "intro" | "block" | "outro"
    block_index: int | None
    start_ms: int
    end_ms: int


def build_reordered_audio(
    file_path: str,
    result: AnalysisResult,
    order: list[int],
    include_intro: bool = True,
    include_outro: bool = True,
) -> AudioSegment:
    audio = AudioSegment.from_file(file_path)

    intro_end_ms = sec_to_ms(result.intro_sec)
    outro_start_ms = sec_to_ms(result.duration - result.outro_sec)
    intro_seg = audio[:intro_end_ms] if include_intro else AudioSegment.empty()
    outro_seg = audio[outro_start_ms:] if include_outro else AudioSegment.empty()

    block_segs = [audio[sec_to_ms(b.start_sec):sec_to_ms(b.end_sec)] for b in result.blocks]

    reordered = AudioSegment.empty()
    for i in order:
        reordered += block_segs[i]

    return intro_seg + reordered + outro_seg


def build_timeline(
    result: AnalysisResult,
    order: list[int],
    include_intro: bool = True,
    include_outro: bool = True,
) -> list[TimelineEntry]:
    timeline: list[TimelineEntry] = []
    cursor = 0

    if include_intro:
        intro_dur = sec_to_ms(result.intro_sec)
        timeline.append(TimelineEntry("intro", None, cursor, cursor + intro_dur))
        cursor += intro_dur

    for i in order:
        block = result.blocks[i]
        dur = sec_to_ms(block.end_sec - block.start_sec)
        timeline.append(TimelineEntry("block", i, cursor, cursor + dur))
        cursor += dur

    if include_outro:
        outro_dur = sec_to_ms(result.outro_sec)
        timeline.append(TimelineEntry("outro", None, cursor, cursor + outro_dur))
        cursor += outro_dur

    return timeline


def total_included_seconds(result: AnalysisResult, order: list[int], include_intro: bool, include_outro: bool) -> float:
    total = result.intro_sec if include_intro else 0.0
    for i in order:
        block = result.blocks[i]
        total += block.end_sec - block.start_sec
    total += result.outro_sec if include_outro else 0.0
    return total


@dataclass
class SongAudioSpec:
    """1曲分の「並び替え・スキップ後の音源」を作るのに必要な情報。
    file_path/resultがNoneの場合は「そのスロットは未読込」を表す。
    """

    file_path: str | None
    result: AnalysisResult | None
    order: list[int] = field(default_factory=list)
    include_intro: bool = True
    include_outro: bool = True

    @property
    def is_ready(self) -> bool:
        return self.file_path is not None and self.result is not None


@dataclass
class JunctionConfig:
    """フロントエンドから受け取る接続部設定（エイト数ベース）"""

    fade_eights: float
    fade_pattern: str = DEFAULT_FADE_PATTERN
    match_bpm: bool = False


@dataclass
class JunctionSpec:
    """音声結合に使う、ms換算済みの接続部設定。
    crossfade_msは「要求値」（エイト数から換算した、まだ曲の長さでクランプする前の値）。
    """

    crossfade_ms: int
    fade_pattern: str = DEFAULT_FADE_PATTERN
    match_bpm: bool = False


@dataclass
class CombinedTimelineEntry:
    song_index: int
    kind: str
    block_index: int | None
    start_ms: int
    end_ms: int


@dataclass
class ResolvedJunction:
    reference_bpm: float | None
    requested_ms: int
    effective_ms: int


def _crossfade_join(
    audio_left: AudioSegment,
    audio_right: AudioSegment,
    junction: JunctionSpec,
    bpm_left: float | None,
    bpm_right: float | None,
) -> AudioSegment:
    """audio_leftの末尾とaudio_rightの先頭を、junctionの設定でクロスフェード結合する。

    match_bpm=Trueの場合、audio_rightのうちクロスフェードにかかる先頭部分だけをbpm_leftに
    合わせてタイムストレッチ（ピッチは維持）し、クロスフェードが終わった後は本来のBPMに戻る。
    """
    crossfade_ms = junction.crossfade_ms
    if junction.match_bpm and bpm_left and bpm_right and crossfade_ms > 0 and bpm_right > 0:
        rate = bpm_left / bpm_right
        # クロスフェード後の長さがcrossfade_msになるよう、伸縮前のスライス長を逆算する
        raw_head_ms = min(int(round(crossfade_ms * rate)), len(audio_right))
        head = audio_right[:raw_head_ms]
        rest = audio_right[raw_head_ms:]
        stretched_head = time_stretch_segment(head, bpm_right, bpm_left)
        combined = concat_with_crossfade([audio_left, stretched_head], crossfade_ms, junction.fade_pattern)
        return combined + rest
    return concat_with_crossfade([audio_left, audio_right], crossfade_ms, junction.fade_pattern)


def build_multi_combined_audio(songs: list[SongAudioSpec], junctions: list[JunctionSpec]) -> AudioSegment:
    """複数曲それぞれの「並び替え・スキップ後の音源」を作り、順にクロスフェードで結合する。

    songs[i]とsongs[i+1]の間の接続設定はjunctions[i]（長さ len(songs)-1 を想定）。
    読み込まれていない曲はスキップし、実際に隣り合う読み込み済みの曲同士を、間にあった
    junction設定（左側の曲のインデックス基準）で結合する。
    """
    ready = [(i, spec) for i, spec in enumerate(songs) if spec.is_ready]
    if not ready:
        raise ValueError("音源が読み込まれていません")

    first_idx, first_spec = ready[0]
    combined = build_reordered_audio(
        first_spec.file_path, first_spec.result, first_spec.order, first_spec.include_intro, first_spec.include_outro
    )
    prev_bpm = first_spec.result.bpm
    prev_idx = first_idx

    for idx, spec in ready[1:]:
        audio = build_reordered_audio(spec.file_path, spec.result, spec.order, spec.include_intro, spec.include_outro)
        junction = junctions[min(prev_idx, len(junctions) - 1)]
        combined = _crossfade_join(combined, audio, junction, prev_bpm, spec.result.bpm)
        prev_bpm = spec.result.bpm
        prev_idx = idx

    return combined


# ---- 接続部（junction）の秒数換算・タイムライン計算 ----
# gui_app.pyのMainWindowインスタンスメソッド（_junction_reference_bpm等）として
# 実装されていたロジックを、明示的な引数を取る純粋関数として書き起こしたもの。


def junction_reference_bpm(left_result: AnalysisResult | None, right_result: AnalysisResult | None) -> float | None:
    """接続部のエイト数→秒数換算に使うBPM（左の曲優先、なければ右の曲）"""
    if left_result is not None:
        return left_result.bpm
    if right_result is not None:
        return right_result.bpm
    return None


def requested_crossfade_ms(reference_bpm: float | None, fade_eights: float) -> int:
    if not reference_bpm or reference_bpm <= 0:
        return 0
    seconds_per_eight = 60 / reference_bpm * 8
    return sec_to_ms(fade_eights * seconds_per_eight)


def junction_bpm_match_rate(match_bpm: bool, bpm_left: float | None, bpm_right: float | None) -> float:
    """BPM調整ON時、右の曲のクロスフェード区間に適用される速度倍率（stretched = original / rate）。OFFなら1.0。"""
    if not match_bpm:
        return 1.0
    if not bpm_left or not bpm_right:
        return 1.0
    return bpm_left / bpm_right


def effective_crossfade_ms(
    requested_ms: int, left_ready: bool, right_ready: bool, t_left_ms: int, t_right_ms: int, rate: float
) -> int:
    """左右の曲の長さ（BPM調整後の換算込み）を超えないようクランプしたクロスフェード長"""
    if not (left_ready and right_ready):
        return 0
    max_cf_from_right = t_right_ms / rate if rate > 0 else t_right_ms
    max_cf = max(0, min(t_left_ms, max_cf_from_right) - 1)
    return max(0, min(requested_ms, max_cf))


def map_time(original_ms: int, raw_head_ms: int, rate: float) -> int:
    """曲の元のタイムライン上の時刻を、結合後（クロスフェード区間のみ伸縮）の時刻に変換する"""
    if rate == 1.0 or original_ms <= raw_head_ms:
        return int(round(original_ms / rate))
    stretched_head_ms = int(round(raw_head_ms / rate))
    return stretched_head_ms + (original_ms - raw_head_ms)


def _slot_result(songs: list[SongAudioSpec], index: int) -> AnalysisResult | None:
    if 0 <= index < len(songs):
        return songs[index].result
    return None


def _slot_ready(songs: list[SongAudioSpec], index: int) -> bool:
    if 0 <= index < len(songs):
        return songs[index].is_ready
    return False


def _slot_total_ms(songs: list[SongAudioSpec], index: int) -> int:
    if 0 <= index < len(songs):
        spec = songs[index]
        if spec.result is not None:
            return sec_to_ms(
                total_included_seconds(spec.result, spec.order, spec.include_intro, spec.include_outro)
            )
    return 0


def resolve_junctions(songs: list[SongAudioSpec], junction_configs: list[JunctionConfig]) -> list[ResolvedJunction]:
    """各接続部の基準BPM・要求クロスフェード長・実効クロスフェード長を計算する
    （画面の「≈X.X秒 / 基準BPM...」ヒント表示に使う）。
    """
    resolved: list[ResolvedJunction] = []
    for i, config in enumerate(junction_configs):
        left_result = _slot_result(songs, i)
        right_result = _slot_result(songs, i + 1)
        reference_bpm = junction_reference_bpm(left_result, right_result)
        requested_ms = requested_crossfade_ms(reference_bpm, config.fade_eights)

        bpm_left = left_result.bpm if left_result is not None else None
        bpm_right = right_result.bpm if right_result is not None else None
        rate = junction_bpm_match_rate(config.match_bpm, bpm_left, bpm_right)

        effective_ms = effective_crossfade_ms(
            requested_ms,
            _slot_ready(songs, i),
            _slot_ready(songs, i + 1),
            _slot_total_ms(songs, i),
            _slot_total_ms(songs, i + 1),
            rate,
        )

        resolved.append(ResolvedJunction(reference_bpm=reference_bpm, requested_ms=requested_ms, effective_ms=effective_ms))
    return resolved


def resolve_junction_specs(songs: list[SongAudioSpec], junction_configs: list[JunctionConfig]) -> list[JunctionSpec]:
    """build_multi_combined_audioに渡すための、ms換算済みJunctionSpec一覧を作る"""
    resolved = resolve_junctions(songs, junction_configs)
    return [
        JunctionSpec(crossfade_ms=r.requested_ms, fade_pattern=config.fade_pattern, match_bpm=config.match_bpm)
        for r, config in zip(resolved, junction_configs)
    ]


def build_combined_timeline(
    songs: list[SongAudioSpec], junction_configs: list[JunctionConfig]
) -> list[CombinedTimelineEntry]:
    """複数曲を結合した際の最終タイムライン（各曲の各パート＝イントロ/ブロック/アウトロが
    結合後の何msから何msかを表すリスト）を計算する。読み込まれていないスロットは除外される。

    各接続の「どのjunction設定（フェード長・パターン・BPM調整有無）を使うか」は
    junction_configs[min(prev_song_index, len-1)]という固定スロット位置で決める
    （曲スロットが空いている場合、build_multi_combined_audioと同じ規則で選ばれる）。
    一方、実際にBPM調整・クロスフェード長のクランプに使うBPM・長さは、常に「今回
    実際に結合される直前の曲」と「今回の曲」自身の値を使う。固定スロット側のBPM・準備状態を
    見てしまうと、間に空きスロットがある場合に実際の音声（build_multi_combined_audioは
    常に実在する隣接曲同士のBPMでクロスフェード・BPM調整する）とタイムラインの計算結果が
    食い違うため（曲スロットが空でBPM調整ONのケースで実際に発生を確認し、意図的にこう
    実装している）。
    """
    timeline: list[CombinedTimelineEntry] = []
    prev_song_index: int | None = None
    prev_last_end_ms = 0

    for i, spec in enumerate(songs):
        if not spec.is_ready:
            continue
        own_timeline = build_timeline(spec.result, spec.order, spec.include_intro, spec.include_outro)

        if prev_song_index is None:
            for e in own_timeline:
                timeline.append(CombinedTimelineEntry(i, e.kind, e.block_index, e.start_ms, e.end_ms))
            prev_last_end_ms = own_timeline[-1].end_ms if own_timeline else 0
            prev_song_index = i
            continue

        prev_spec = songs[prev_song_index]  # 常にready（readyな曲だけがprev_song_indexになる）
        junction_index = min(prev_song_index, len(junction_configs) - 1)
        config = junction_configs[junction_index]

        rate = junction_bpm_match_rate(config.match_bpm, prev_spec.result.bpm, spec.result.bpm)
        reference_bpm = junction_reference_bpm(prev_spec.result, spec.result)
        requested_ms = requested_crossfade_ms(reference_bpm, config.fade_eights)

        t_left_ms = sec_to_ms(
            total_included_seconds(prev_spec.result, prev_spec.order, prev_spec.include_intro, prev_spec.include_outro)
        )
        t_right_ms = sec_to_ms(
            total_included_seconds(spec.result, spec.order, spec.include_intro, spec.include_outro)
        )
        cf_ms = effective_crossfade_ms(requested_ms, True, True, t_left_ms, t_right_ms, rate)

        raw_head_ms = min(int(round(cf_ms * rate)), t_right_ms)
        offset = max(0, prev_last_end_ms - cf_ms)

        last_end = offset
        for e in own_timeline:
            start = map_time(e.start_ms, raw_head_ms, rate) + offset
            end = map_time(e.end_ms, raw_head_ms, rate) + offset
            timeline.append(CombinedTimelineEntry(i, e.kind, e.block_index, start, end))
            last_end = end

        prev_last_end_ms = last_end
        prev_song_index = i

    return timeline
