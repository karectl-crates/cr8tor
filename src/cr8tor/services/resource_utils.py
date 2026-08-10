""" Helpers for reading Resource entries out of a Project CRD spec.

The Project CRD carries its applications and services as a list of Resource entries under
``spec.resources``, each discriminated by ``resource_type`` (the LinkML ``designates_type``
slot). Config for a given service lives on its own entry rather than in a top-level block.
"""


def get_resource_entry(spec, resource_type):
    """ Get the resource entry of a given resource_type from a Project spec.

    Args:
        spec: Project CRD spec dict
        resource_type: Resource subclass discriminator, e.g. "Jupyter", "VDI", "Gitea"

    Returns:
        The matching resource dict, or an empty dict when the resource is not present.
    """
    for entry in (spec or {}).get("resources") or []:
        if entry.get("resource_type") == resource_type:
            return entry
    return {}
