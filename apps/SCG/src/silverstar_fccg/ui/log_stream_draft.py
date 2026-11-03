"""Apply supported stream edits while retaining required system records."""
from silverstar_fccg.core.view_models import LoggingStreamView
from silverstar_fccg.project.model import LogStreamConfig, ProjectModel
from silverstar_fccg.project.feature_tiers import FeatureTier_LogRecordAllowed, FeatureTier_LogRecordRequired


def LoggingSnapshot_Apply(
    model: ProjectModel,
    stream_views: tuple[LoggingStreamView, ...],
) -> None:
    if model.build.logging_profile != "all_streams":
        return
    if stream_views:
        retained = {stream.record: stream for stream in model.logging_streams}
        model.logging_streams = [
            retained[stream.stream_id]
            if ((not FeatureTier_LogRecordAllowed(model, stream.stream_id) or
                 FeatureTier_LogRecordRequired(model, stream.stream_id)) and stream.stream_id in retained)
            else LogStreamConfig(
                record=stream.stream_id,
                enabled=stream.enabled,
                policy=stream.policy,
                decimation=stream.decimation,
                period_us=stream.period_us,
            )
            for stream in stream_views
        ]
