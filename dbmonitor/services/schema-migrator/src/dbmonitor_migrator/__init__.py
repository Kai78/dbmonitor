from dbmonitor_migrator.platform_migrations import apply_platform_migrations
from dbmonitor_migrator.plugin_runner import apply_plugin_bundle_migrations, physical_table_name

__all__ = [
    "apply_platform_migrations",
    "apply_plugin_bundle_migrations",
    "physical_table_name",
]
