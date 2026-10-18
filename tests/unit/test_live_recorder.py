"""Real-time movie recording (V-68): the recorder's clock logic, a real encode, and the window's controls."""
import numpy as np
import pytest

from pyfds.results.viz import recorder as rec


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def img(v=0, w=64, h=48):
    return np.full((h, w, 3), v, dtype=np.uint8)


def test_frames_follow_the_clock_not_the_redraw_rate(tmp_path):
    c = Clock()
    r = rec.LiveRecorder(str(tmp_path / "a.mp4"), fps=10, clock=c, ffmpeg=None)
    r.start()
    assert r.add_frame(img()) == 1                  # first picture is frame 0
    c.t += 0.5                                      # a slow redraw: half a second passed
    assert r.add_frame(img()) == 5                  # five film frames fill the gap
    assert r.frames == 6 and r.elapsed == pytest.approx(0.5)


def test_pause_does_not_count_and_adds_nothing(tmp_path):
    c = Clock()
    r = rec.LiveRecorder(str(tmp_path / "a.mp4"), fps=10, clock=c, ffmpeg=None)
    r.start()
    r.add_frame(img())
    c.t += 0.2
    r.pause()
    c.t += 30.0
    assert r.add_frame(img()) == 0
    r.resume()
    assert r.elapsed == pytest.approx(0.2)
    c.t += 0.1
    r.add_frame(img())
    assert r.elapsed == pytest.approx(0.3) and r.frames == 4


def test_without_an_encoder_numbered_pngs_are_kept(tmp_path):
    c = Clock()
    r = rec.LiveRecorder(str(tmp_path / "clip.mp4"), fps=5, clock=c, ffmpeg=None)
    r.start()
    for _ in range(3):
        r.add_frame(img(7))
        c.t += 0.2
    res = r.stop()
    assert not res["encoded"] and res["frames"] == 3
    from pathlib import Path
    assert sorted(p.name for p in Path(res["frames_dir"]).iterdir()) == ["clip_00000.png", "clip_00001.png", "clip_00002.png"]


def test_state_errors(tmp_path):
    r = rec.LiveRecorder(str(tmp_path / "a.mp4"), ffmpeg=None)
    with pytest.raises(RuntimeError):
        r.pause()
    with pytest.raises(RuntimeError):
        r.stop()
    r.start()
    with pytest.raises(RuntimeError):
        r.start()
    with pytest.raises(RuntimeError):
        r.resume()
    with pytest.raises(ValueError):
        rec.LiveRecorder("x.mp4", fps=0)


def test_odd_and_changing_sizes_are_fitted(tmp_path):
    c = Clock()
    r = rec.LiveRecorder(str(tmp_path / "a.mp4"), fps=10, clock=c, ffmpeg=None)
    r.start()
    r.add_frame(img(w=65, h=49))
    assert r.size == (64, 48)
    c.t += 0.1
    r.add_frame(img(w=40, h=30))                    # window shrank: padded, not an error
    c.t += 0.1
    r.add_frame(np.zeros((60, 80, 4), dtype=np.uint8))     # grew, with alpha: cropped
    assert r.frames == 3


@pytest.mark.skipif(rec.encoder_path() is None, reason="no ffmpeg")
def test_real_mp4_is_written(tmp_path):
    c = Clock()
    out = tmp_path / "film.mp4"
    r = rec.LiveRecorder(str(out), fps=10, clock=c)
    r.start()
    for i in range(10):
        r.add_frame(img(i * 20))
        c.t += 0.1
    res = r.stop()
    assert res["encoded"] and out.stat().st_size > 500 and res["frames"] == 10
