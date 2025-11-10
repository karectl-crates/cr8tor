#!/usr/bin/env python3
"""Generate CRDs without full dependencies - Demo"""

import yaml
import json
import hashlib
from pathlib import Path


def generate_demo_crds():
    """Generate demo CRDs to show the structure."""
    output_dir = Path("crds/generated")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define CRDs
    crds = [
        {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": "users.identity.karectl.io"},
            "spec": {
                "group": "identity.karectl.io",
                "versions": [
                    {
                        "name": "v1alpha1",
                        "served": True,
                        "storage": True,
                        "schema": {
                            "openAPIV3Schema": {
                                "type": "object",
                                "properties": {
                                    "spec": {
                                        "type": "object",
                                        "properties": {
                                            "username": {"type": "string"},
                                            "email": {"type": "string"},
                                            "enabled": {
                                                "type": "boolean",
                                                "default": True,
                                            },
                                            "groups": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                            "keycloak": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                            "jupyterhub": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                            "karectl": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                        },
                                        "required": ["username", "email"],
                                    },
                                    "status": {
                                        "type": "object",
                                        "properties": {
                                            "phase": {"type": "string"},
                                            "conditions": {
                                                "type": "array",
                                                "items": {"type": "object"},
                                            },
                                            "observedGeneration": {"type": "integer"},
                                        },
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["spec"],
                            }
                        },
                        "subresources": {"status": {}},
                    }
                ],
                "scope": "Namespaced",
                "names": {
                    "plural": "users",
                    "singular": "user",
                    "kind": "User",
                    "shortNames": ["usr"],
                },
            },
        },
        {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": "groups.identity.karectl.io"},
            "spec": {
                "group": "identity.karectl.io",
                "versions": [
                    {
                        "name": "v1alpha1",
                        "served": True,
                        "storage": True,
                        "schema": {
                            "openAPIV3Schema": {
                                "type": "object",
                                "properties": {
                                    "spec": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "description": {"type": "string"},
                                            "attributes": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                            "members": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        },
                                        "required": ["name"],
                                    },
                                    "status": {
                                        "type": "object",
                                        "properties": {
                                            "phase": {"type": "string"},
                                            "conditions": {
                                                "type": "array",
                                                "items": {"type": "object"},
                                            },
                                            "observedGeneration": {"type": "integer"},
                                        },
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["spec"],
                            }
                        },
                        "subresources": {"status": {}},
                    }
                ],
                "scope": "Namespaced",
                "names": {
                    "plural": "groups",
                    "singular": "group",
                    "kind": "Group",
                    "shortNames": ["grp"],
                },
            },
        },
        {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": "keycloakclients.identity.karectl.io"},
            "spec": {
                "group": "identity.karectl.io",
                "versions": [
                    {
                        "name": "v1alpha1",
                        "served": True,
                        "storage": True,
                        "schema": {
                            "openAPIV3Schema": {
                                "type": "object",
                                "properties": {
                                    "spec": {
                                        "type": "object",
                                        "properties": {
                                            "clientId": {"type": "string"},
                                            "name": {"type": "string"},
                                            "secret": {"type": "string"},
                                            "secretRef": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "key": {"type": "string"},
                                                },
                                            },
                                            "enabled": {
                                                "type": "boolean",
                                                "default": True,
                                            },
                                            "publicClient": {
                                                "type": "boolean",
                                                "default": False,
                                            },
                                            "redirectUris": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                            "webOrigins": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                            "protocol": {
                                                "type": "string",
                                                "default": "openid-connect",
                                            },
                                            "defaultClientScopes": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                            "optionalClientScopes": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                            "protocolMappers": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "x-kubernetes-preserve-unknown-fields": True,
                                                },
                                            },
                                            "attributes": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                            "additionalConfig": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                        },
                                        "required": ["clientId"],
                                    },
                                    "status": {
                                        "type": "object",
                                        "properties": {
                                            "phase": {"type": "string"},
                                            "conditions": {
                                                "type": "array",
                                                "items": {"type": "object"},
                                            },
                                            "observedGeneration": {"type": "integer"},
                                        },
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["spec"],
                            }
                        },
                        "subresources": {"status": {}},
                    }
                ],
                "scope": "Namespaced",
                "names": {
                    "plural": "keycloakclients",
                    "singular": "keycloakclient",
                    "kind": "KeycloakClient",
                    "shortNames": ["kcc"],
                },
            },
        },
        {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": "vdiinstances.karectl.io"},
            "spec": {
                "group": "karectl.io",
                "versions": [
                    {
                        "name": "v1alpha1",
                        "served": True,
                        "storage": True,
                        "schema": {
                            "openAPIV3Schema": {
                                "type": "object",
                                "properties": {
                                    "spec": {
                                        "type": "object",
                                        "properties": {
                                            "user": {"type": "string"},
                                            "project": {"type": "string"},
                                            "image": {
                                                "type": "string",
                                                "default": "ghcr.io/karectl/vdi-mate:v1.0.0-light",
                                            },
                                            "connection": {
                                                "type": "string",
                                                "default": "rdp",
                                            },
                                            "env": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "name": {"type": "string"},
                                                        "value": {"type": "string"},
                                                    },
                                                    "required": ["name", "value"],
                                                },
                                            },
                                            "resources": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                            "storage": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                            "networking": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                        },
                                        "required": ["user", "project"],
                                    },
                                    "status": {
                                        "type": "object",
                                        "properties": {
                                            "phase": {"type": "string"},
                                            "conditions": {
                                                "type": "array",
                                                "items": {"type": "object"},
                                            },
                                            "observedGeneration": {"type": "integer"},
                                        },
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["spec"],
                            }
                        },
                        "subresources": {"status": {}},
                    }
                ],
                "scope": "Namespaced",
                "names": {
                    "plural": "vdiinstances",
                    "singular": "vdiinstance",
                    "kind": "VDIInstance",
                    "shortNames": ["vdi"],
                },
            },
        },
    ]

    # Write CRD files
    filenames = []
    for crd in crds:
        filename = f"{crd['metadata']['name']}.yaml"
        filepath = output_dir / filename

        with open(filepath, "w") as f:
            yaml.dump(crd, f, default_flow_style=False, sort_keys=False)

        filenames.append(filename)
        print(f"Generated: {filename}")

    # Generate kustomization.yaml
    kustomization = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": sorted(filenames),
    }

    with open(output_dir / "kustomization.yaml", "w") as f:
        yaml.dump(kustomization, f, default_flow_style=False)

    print("Generated: kustomization.yaml")

    # Generate hash file
    model_data = json.dumps(crds, sort_keys=True)
    model_hash = hashlib.sha256(model_data.encode()).hexdigest()

    with open(output_dir / ".models_hash", "w") as f:
        f.write(model_hash)

    print("Generated: .models_hash")
    print(f"Generated {len(crds)} CRD files")


if __name__ == "__main__":
    print("Generating Demo CRDs")
    print("=" * 40)
    generate_demo_crds()
    print("Demo CRD generation complete!")
