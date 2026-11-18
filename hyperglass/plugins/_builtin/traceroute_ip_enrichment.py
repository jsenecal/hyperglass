"""Optional IP and ASN enrichment for structured traceroute data."""

import asyncio
import typing as t

from pydantic import PrivateAttr

from hyperglass.log import log
from hyperglass.state import use_state
from hyperglass.plugins._output import OutputPlugin
from hyperglass.models.data.traceroute import TracerouteResult

if t.TYPE_CHECKING:
    from hyperglass.models.data import OutputDataModel
    from hyperglass.models.api.query import Query


class ZTracerouteIpEnrichment(OutputPlugin):
    """Enrich traceroute addresses while preserving router-provided hostnames."""

    _hyperglass_builtin: bool = PrivateAttr(True)
    platforms: t.Sequence[str] = ()
    directives: t.Sequence[str] = ()
    common: bool = True

    async def enrich(self, output: TracerouteResult) -> None:
        """Enrich IP and ASN metadata without supplemental reverse DNS requests."""
        await output.enrich_with_ip_enrichment()
        await output.enrich_asn_organizations()

    def process(self, *, output: "OutputDataModel", query: "Query") -> "OutputDataModel":
        """Apply optional enrichment in the output-processing worker thread."""
        if not isinstance(output, TracerouteResult):
            return output
        config = use_state("params").structured.ip_enrichment
        if not config.enrich_traceroute or config.mode == "async":
            return output
        try:
            asyncio.run(self.enrich(output))
        except Exception as error:
            log.bind(error=str(error)).error("Traceroute enrichment failed")
        return output
