"""Device model for Off-grid Protection."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OffGridDevice:
    """Represent one device managed by Off-grid Protection."""

    id: str
    name: str
    device_type: str
    entity_id: str
    type_config: dict[str, Any] = field(default_factory=dict)
    automations: list[str] = field(default_factory=list)
    override: dict[str, Any] = field(default_factory=dict)

    # Resources created by OGP for this device.
    #
    # IMPORTANT:
    # Only resources actually created by OGP belong here.
    # Existing/user-created automations selected in ``automations``
    # are NOT copied into this list and therefore are never deleted
    # by OGP cleanup.
    generated_resources: dict[str, list[str]] = field(
        default_factory=lambda: {
            "entities": [],
            "automations": [],
            "helpers": [],
        }
    )

    @property
    def shutdown_action(self) -> Any:
        """Return the configured shutdown action."""

        return self.type_config.get(
            "shutdown_action",
            "turn_off",
        )

    @property
    def off_state(self) -> str:
        """Return the configured OFF state."""

        return self.type_config.get(
            "off_state",
            "off",
        )

    @property
    def wait_for_unavailable(self) -> bool:
        """Return whether unavailable state should be awaited."""

        return self.type_config.get(
            "wait_for_unavailable",
            True,
        )

    @property
    def recovery_timeout(self) -> int:
        """Return the recovery timeout in seconds."""

        return int(
            self.type_config.get(
                "recovery_timeout",
                180,
            )
        )

    @property
    def command_timeout(self) -> int:
        """Return the shutdown command timeout in seconds."""

        return int(
            self.type_config.get(
                "command_timeout",
                15,
            )
        )

    @property
    def override_enabled(self) -> bool:
        """Return whether override is enabled."""

        return self.override.get(
            "override_enabled",
            True,
        )

    @property
    def require_pin(self) -> bool:
        """Return whether PIN is required."""

        return self.override.get(
            "require_pin",
            True,
        )

    @property
    def minimum_runtime(self) -> int:
        """Return the minimum override runtime in minutes."""

        return int(
            self.override.get(
                "minimum_runtime",
                1,
            )
        )

    @property
    def maximum_runtime(self) -> int:
        """Return the maximum override runtime in minutes."""

        return int(
            self.override.get(
                "maximum_runtime",
                60,
            )
        )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "OffGridDevice":
        """Create a device from stored configuration."""

        generated = data.get(
            "generated_resources",
            {},
        )

        generated_resources = {
            "entities": list(
                generated.get(
                    "entities",
                    [],
                )
            ),
            "automations": list(
                generated.get(
                    "automations",
                    [],
                )
            ),
            "helpers": list(
                generated.get(
                    "helpers",
                    [],
                )
            ),
        }

        return cls(
            id=data["id"],
            name=data["name"],
            device_type=data["type"],
            entity_id=data["entity_id"],
            type_config=dict(
                data.get(
                    "type_config",
                    {},
                )
            ),
            automations=list(
                data.get(
                    "automations",
                    [],
                )
            ),
            override=dict(
                data.get(
                    "override",
                    {},
                )
            ),
            generated_resources=generated_resources,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the device to stored configuration."""

        return {
            "id": self.id,
            "name": self.name,
            "type": self.device_type,
            "entity_id": self.entity_id,
            "type_config": dict(
                self.type_config
            ),
            "automations": list(
                self.automations
            ),
            "override": {
                **self.override,
            },
            "generated_resources": {
                "entities": list(
                    self.generated_resources.get(
                        "entities",
                        [],
                    )
                ),
                "automations": list(
                    self.generated_resources.get(
                        "automations",
                        [],
                    )
                ),
                "helpers": list(
                    self.generated_resources.get(
                        "helpers",
                        [],
                    )
                ),
            },
        }

    def add_generated_resource(
        self,
        resource_type: str,
        resource_id: str,
    ) -> None:
        """Record a resource created by OGP."""

        resources = self.generated_resources.setdefault(
            resource_type,
            [],
        )

        if resource_id not in resources:
            resources.append(resource_id)

    def remove_generated_resource(
        self,
        resource_type: str,
        resource_id: str,
    ) -> None:
        """Remove a generated resource from the ownership record."""

        resources = self.generated_resources.get(
            resource_type,
            [],
        )

        if resource_id in resources:
            resources.remove(resource_id)
