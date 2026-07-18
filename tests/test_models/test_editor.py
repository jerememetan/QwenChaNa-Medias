"""Editor model contracts."""

import pytest
from pydantic import ValidationError

from models.editor import EditorOutput, SceneMedia


def test_scene_media_requires_at_least_one_clip():
    with pytest.raises(ValidationError):
        SceneMedia(scene_number=1, clip_paths=[], narration_path="voice.mp3")


def test_scene_media_accepts_ordered_clips():
    media = SceneMedia(
        scene_number=2,
        clip_paths=["shot_002.mp4", "shot_003.mp4"],
        narration_path="scene_002.mp3",
    )
    assert media.clip_paths == ["shot_002.mp4", "shot_003.mp4"]


def test_editor_output_records_final_path_and_scene_count():
    output = EditorOutput(
        final_path="outputs/job/editor/final/final_video.mp4",
        scene_count=2,
    )
    assert output.scene_count == 2


def test_editor_output_rejects_zero_scenes():
    with pytest.raises(ValidationError):
        EditorOutput(final_path="final.mp4", scene_count=0)
