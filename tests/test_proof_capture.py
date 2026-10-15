from PIL import Image
import pytest

from windowrift.proof_capture import ProofRecorder


def test_records_real_frames_at_bounded_interval_and_writes_gif(tmp_path):
    recorder = ProofRecorder(interval=0.2, max_frames=3, max_width=400)
    assert recorder.add_frame(0.0, Image.new('RGB', (800, 600), 'red'))
    assert not recorder.add_frame(0.1, Image.new('RGB', (800, 600), 'white'))
    assert recorder.add_frame(0.2, Image.new('RGB', (800, 600), 'blue'))
    assert recorder.add_frame(0.4, Image.new('RGB', (800, 600), 'green'))
    assert not recorder.add_frame(1, Image.new('RGB', (800, 600), 'yellow'))
    output = tmp_path / 'proof.gif'
    assert recorder.save(output) == 3
    with Image.open(output) as image:
        assert image.n_frames == 3
        assert image.size == (400, 300)


def test_refuses_invalid_recording_or_empty_frame_list(tmp_path):
    with pytest.raises(ValueError):
        ProofRecorder(interval=0)
    with pytest.raises(ValueError):
        ProofRecorder(max_frames=121)
    with pytest.raises(ValueError):
        ProofRecorder(max_width=20)
    with pytest.raises(ValueError):
        ProofRecorder().save(tmp_path / 'empty.gif')
