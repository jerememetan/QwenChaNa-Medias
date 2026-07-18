"""Editor model contracts."""

import pytest
from pydantic import ValidationError

from models.editor import ClipMedia, EditorOutput, SceneMedia


def test_scene_media_requires_at_least_one_clip():
    with pytest.raises(ValidationError):
        SceneMedia(
            scene_number=1,
            clips=[],
            narration_path="voice.mp3",
            planned_duration=1,
        )


def test_scene_media_accepts_ordered_clips():
    media = SceneMedia(
        scene_number=2,
        clips=[
            ClipMedia(
                shot_number=2,
                file_path="shot_002.mp4",
                planned_duration=0.65,
            ),
            ClipMedia(
                shot_number=3,
                file_path="shot_003.mp4",
                planned_duration=4.35,
            ),
        ],
        narration_path="scene_002.mp3",
        planned_duration=5,
    )
    assert [clip.shot_number for clip in media.clips] == [2, 3]
    assert [clip.planned_duration for clip in media.clips] == [0.65, 4.35]


@pytest.mark.parametrize("duration", [0, -1])
def test_clip_media_rejects_non_positive_planned_duration(duration):
    with pytest.raises(ValidationError):
        ClipMedia(
            shot_number=1,
            file_path="shot.mp4",
            planned_duration=duration,
        )


def test_editor_output_records_final_path_and_scene_count():
    output = EditorOutput(
        final_path="outputs/job/editor/final/final_video.mp4",
        scene_count=2,
    )
    assert output.scene_count == 2


def test_editor_output_rejects_zero_scenes():
    with pytest.raises(ValidationError):
        EditorOutput(final_path="final.mp4", scene_count=0)
