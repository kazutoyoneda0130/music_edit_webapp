"""
music_engine.audio_engine の動作検証テスト。

音声処理ロジックは元々 music_edit_app/gui_app.py（PySide6デスクトップアプリ）の
MainWindowインスタンスメソッドとして実装されていたものを、UIに依存しない純粋関数として
書き起こしたもの。ここでは実際に合成音源を使って結合結果・タイムライン計算の正しさを検証する。
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from pydub import AudioSegment
from scipy.signal import find_peaks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from music_engine.analyze_bpm import build_blocks, detect_beats
from music_engine.audio_engine import (
    JunctionConfig,
    SongAudioSpec,
    build_combined_timeline,
    build_multi_combined_audio,
    resolve_junction_specs,
    resolve_junctions,
)

SR = 22050


def make_tone_song(path: Path, bpm: float, block_tone_freq: float, duration_sec: float = 20.0) -> None:
    """イントロ(2s,クリックなし) + クリック付きブロック(block_tone_freq) + アウトロ(2s,クリックなし)"""
    beat_interval = 60 / bpm

    def segment(dur, freq, with_clicks):
        t = np.linspace(0, dur, int(SR * dur), endpoint=False)
        y = 0.12 * np.sin(2 * np.pi * freq * t)
        if with_clicks:
            start = 0.0
            while start < dur - 1e-6:
                idx = int(start * SR)
                y[idx : idx + 300] += 0.5 * np.sin(2 * np.pi * 2000 * t[idx : idx + 300])
                start += beat_interval
        return y

    block_dur = duration_sec - 4.0
    audio = np.concatenate(
        [segment(2.0, 50.0, False), segment(block_dur, block_tone_freq, True), segment(2.0, 60.0, False)]
    )
    sf.write(path, audio, SR)


def load_song_spec(path: str, unit: int = 4) -> SongAudioSpec:
    beat_info = detect_beats(path)
    result = build_blocks(beat_info, unit)
    order = list(range(len(result.blocks)))
    return SongAudioSpec(path, result, order, True, True)


def dominant_freq(seg: AudioSegment, t_start: float, t_end: float) -> float:
    sr = seg.frame_rate
    samples = np.array(seg.get_array_of_samples()).astype(np.float64) / 32768.0
    region = samples[int(t_start * sr) : int(t_end * sr)]
    windowed = region * np.hanning(len(region))
    spec = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(region), 1 / sr)
    mask = (freqs > 30) & (freqs < 2000)
    return float(freqs[mask][np.argmax(spec[mask])])


@pytest.fixture()
def two_songs(tmp_path: Path) -> tuple[str, str]:
    p1 = tmp_path / "song1.wav"
    p2 = tmp_path / "song2.wav"
    make_tone_song(p1, bpm=120, block_tone_freq=300.0)
    make_tone_song(p2, bpm=150, block_tone_freq=900.0)
    return str(p1), str(p2)


@pytest.fixture()
def three_songs(tmp_path: Path) -> tuple[str, str, str]:
    p1 = tmp_path / "song1.wav"
    p2 = tmp_path / "song2.wav"
    p3 = tmp_path / "song3.wav"
    make_tone_song(p1, bpm=120, block_tone_freq=300.0)
    make_tone_song(p2, bpm=150, block_tone_freq=900.0)
    make_tone_song(p3, bpm=100, block_tone_freq=1300.0)
    return str(p1), str(p2), str(p3)


def test_combined_timeline_matches_actual_audio_duration(two_songs):
    """timelineの合計msと、実際に生成した音声の長さがほぼ一致することを確認する"""
    path1, path2 = two_songs
    songs = [load_song_spec(path1), load_song_spec(path2)]
    junction_configs = [JunctionConfig(fade_eights=2.0, fade_pattern="equal_power", match_bpm=False)]

    timeline = build_combined_timeline(songs, junction_configs)
    total_ms = timeline[-1].end_ms

    junction_specs = resolve_junction_specs(songs, junction_configs)
    audio = build_multi_combined_audio(songs, junction_specs)

    assert abs(total_ms - len(audio)) <= 2


def test_combined_timeline_matches_audio_with_bpm_match(two_songs):
    """BPM調整ONの場合もtimelineとaudioの長さが一致することを確認する（回帰テスト）"""
    path1, path2 = two_songs
    songs = [load_song_spec(path1), load_song_spec(path2)]
    junction_configs = [JunctionConfig(fade_eights=3.0, fade_pattern="equal_power", match_bpm=True)]

    timeline = build_combined_timeline(songs, junction_configs)
    total_ms = timeline[-1].end_ms

    junction_specs = resolve_junction_specs(songs, junction_configs)
    audio = build_multi_combined_audio(songs, junction_specs)

    assert abs(total_ms - len(audio)) <= 2


def test_gap_scenario_timeline_matches_audio(three_songs):
    """真ん中の曲が未読込（ギャップ）でBPM調整ONの場合でも、timelineとaudioの長さが一致すること。

    これはgui_app.py（デスクトップ版）の移植時に発見した不整合（ギャップ+BPM調整ONの組み合わせで
    timeline側が空きスロットの情報を見てしまい、実際の音声との合計時間が大きくズレる）の回帰テスト。
    """
    path1, _path2, path3 = three_songs
    songs = [
        load_song_spec(path1, unit=2),
        SongAudioSpec(None, None, [], True, True),  # 曲2は未読込（ギャップ）
        load_song_spec(path3, unit=2),
    ]
    junction_configs = [
        JunctionConfig(fade_eights=2.0, fade_pattern="equal_power", match_bpm=True),
        JunctionConfig(fade_eights=2.0, fade_pattern="equal_power", match_bpm=True),
    ]

    timeline = build_combined_timeline(songs, junction_configs)
    total_ms = timeline[-1].end_ms

    junction_specs = resolve_junction_specs(songs, junction_configs)
    audio = build_multi_combined_audio(songs, junction_specs)

    assert abs(total_ms - len(audio)) <= 2
    # 曲1・曲3の音声内容（周波数）が両方含まれていることも確認する
    # （末尾2秒は曲3のアウトロ=60Hzなので、その手前のブロック区間で確認する）
    total_sec = len(audio) / 1000
    assert abs(dominant_freq(audio, 3, 5) - 300.0) < 1
    assert abs(dominant_freq(audio, total_sec - 4, total_sec - 2.5) - 1300.0) < 1


def test_skip_excludes_content_from_output(two_songs):
    """スキップ（チェック）した部分は、結合後の音声に含まれないこと"""
    path1, path2 = two_songs
    spec1 = load_song_spec(path1)
    spec2 = load_song_spec(path2)

    # 曲1のアウトロ・曲2のイントロをスキップ
    spec1 = SongAudioSpec(spec1.file_path, spec1.result, spec1.order, spec1.include_intro, include_outro=False)
    spec2 = SongAudioSpec(spec2.file_path, spec2.result, spec2.order, include_intro=False, include_outro=spec2.include_outro)

    songs = [spec1, spec2]
    junction_configs = [JunctionConfig(fade_eights=2.0, fade_pattern="equal_power", match_bpm=False)]
    junction_specs = resolve_junction_specs(songs, junction_configs)
    audio = build_multi_combined_audio(songs, junction_specs)

    # 末尾2秒は曲2のアウトロ(60Hz)なので、その手前のブロック区間で900Hzを確認する
    total_sec = len(audio) / 1000
    assert abs(dominant_freq(audio, 3, 5) - 300.0) < 1
    assert abs(dominant_freq(audio, total_sec - 4, total_sec - 2.5) - 900.0) < 1


def test_bpm_match_reverts_after_crossfade(two_songs):
    """BPM調整ONの場合、クロスフェード区間だけ左の曲のBPMに合わせられ、
    それ以降は右の曲本来のBPMに戻ることを、クリック間隔の解析で確認する。
    """
    path1, path2 = two_songs
    songs = [load_song_spec(path1), load_song_spec(path2)]
    junction_configs = [JunctionConfig(fade_eights=4.0, fade_pattern="equal_power", match_bpm=True)]

    junction_specs = resolve_junction_specs(songs, junction_configs)
    audio = build_multi_combined_audio(songs, junction_specs)

    sr = audio.frame_rate
    samples = np.array(audio.get_array_of_samples()).astype(np.float64) / 32768.0
    env = np.abs(samples)
    peaks, _ = find_peaks(env, height=0.3, distance=int(sr * 0.1))
    click_times = peaks / sr
    intervals = np.diff(click_times)

    def median_interval(t0, t1):
        mask = (click_times[:-1] >= t0) & (click_times[:-1] < t1)
        return float(np.median(intervals[mask]))

    # 曲1のブロック領域（イントロ2秒の後、120bpm=0.5s間隔のはず）
    assert median_interval(3.0, 4.0) == pytest.approx(0.5, abs=0.02)

    # 末尾はアウトロ(クリックなし)の手前＝曲2のブロック領域。曲2本来の150bpm=0.4s間隔に戻っているはず
    total_sec = len(audio) / 1000
    assert median_interval(total_sec - 4, total_sec - 2.5) == pytest.approx(0.4, abs=0.02)


def test_resolve_junctions_reference_bpm_uses_fixed_slot(three_songs):
    """resolve_junctionsのヒント表示用の基準BPMは、固定スロット位置（junction_index / +1）を
    見る（デスクトップ版のUI表示と同じ仕様）。ギャップがあっても左スロットが読み込み済みなら
    そのBPMが使われる。
    """
    path1, _path2, path3 = three_songs
    songs = [
        load_song_spec(path1),
        SongAudioSpec(None, None, [], True, True),
        load_song_spec(path3),
    ]
    junction_configs = [
        JunctionConfig(fade_eights=1.0, fade_pattern="linear", match_bpm=False),
        JunctionConfig(fade_eights=1.0, fade_pattern="linear", match_bpm=False),
    ]

    resolved = resolve_junctions(songs, junction_configs)
    assert resolved[0].reference_bpm == pytest.approx(songs[0].result.bpm)
    # junction1は左(songs[1])が空なので、右(songs[2])のBPMにフォールバックする
    assert resolved[1].reference_bpm == pytest.approx(songs[2].result.bpm)


def test_all_fade_patterns_produce_valid_audio(two_songs):
    path1, path2 = two_songs
    songs = [load_song_spec(path1), load_song_spec(path2)]

    for pattern in ["linear", "equal_power", "scurve"]:
        junction_configs = [JunctionConfig(fade_eights=1.0, fade_pattern=pattern, match_bpm=False)]
        junction_specs = resolve_junction_specs(songs, junction_configs)
        audio = build_multi_combined_audio(songs, junction_specs)
        assert len(audio) > 0
