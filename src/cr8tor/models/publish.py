""" DataPublishJob CRD model for the operator based data publishing pipeline.
"""

from cr8tor.crd.registry import CRDRegistry
from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import DataPublishJobSpec


@CRDRegistry.register(
    group="publish.karectl.io",
    version="v1alpha1",
    kind="DataPublishJob",
    plural="datapublishjobs",
    scope="Namespaced",
)
class DataPublishJobCRD(DataPublishJobSpec):
    """ DataPublishJob CRD which triggers the operator based data publishing pipeline.
        Uses publish.karectl.io as the API group
    """
    pass
