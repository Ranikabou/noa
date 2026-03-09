"""NOA canonical contracts — Pydantic v2. All 16 contracts."""

from noa_contracts.common import (
    BBox,
    Point2D,
    ScaleInfo,
    ObservationType,
)
from noa_contracts.project import Project
from noa_contracts.floorplan_asset import FloorplanAsset
from noa_contracts.parsed_plan import ParsedPlan
from noa_contracts.spatial_graph import SpatialGraph
from noa_contracts.style_profile import StyleProfile
from noa_contracts.geometry_rule_set import GeometryRuleSet
from noa_contracts.canonical_building_model import CanonicalBuildingModel
from noa_contracts.render_scene import RenderScene
from noa_contracts.render_image import RenderImage
from noa_contracts.export_package import ExportPackage
from noa_contracts.critique_report import CritiqueReport
from noa_contracts.user import User
from noa_contracts.inspiration_board import InspirationBoard
from noa_contracts.inspiration_item import InspirationItem
from noa_contracts.annotation_session import AnnotationSession
from noa_contracts.event_stream import (
    JobUpdateEvent,
    AmbiguityFlagEvent,
    HeartbeatEvent,
)

__all__ = [
    "BBox",
    "Point2D",
    "ScaleInfo",
    "ObservationType",
    "Project",
    "FloorplanAsset",
    "ParsedPlan",
    "SpatialGraph",
    "StyleProfile",
    "GeometryRuleSet",
    "CanonicalBuildingModel",
    "RenderScene",
    "RenderImage",
    "ExportPackage",
    "CritiqueReport",
    "User",
    "InspirationBoard",
    "InspirationItem",
    "AnnotationSession",
    "JobUpdateEvent",
    "AmbiguityFlagEvent",
    "HeartbeatEvent",
]
