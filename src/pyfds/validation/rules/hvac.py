"""HVAC network reference and topology rules."""
from __future__ import annotations

from ._common import _e, _w


from typing import Any, Dict, List, Set
from ..engine import ValidationResult, Severity


class HvacNodeReferenceRule:
    """HVAC ducts and fans refer to nodes that exist."""
    name = "HvacNodeReference"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        node_ids = {n.name for n in p.hvac_nodes}
        for duct in p.hvac_ducts:
            for nid in [duct.node_id_1, duct.node_id_2]:
                if nid and nid not in node_ids:
                    node_ids.add(nid)  # deduplicate across iterations

                    def _fix(project, _nid=nid):
                        from pyfds.domain.model import HvacNode
                        if not any(n.name == _nid for n in project.hvac_nodes):
                            project.add_entity(HvacNode(name=_nid, x=0.0, y=0.0, z=0.0))

                    results.append(ValidationResult(
                        severity=Severity.ERROR,
                        rule=self.name,
                        message=f"DUCT '{duct.name}' references undefined NODE '{nid}'.",
                        entity_name=duct.name,
                        hint=f"Define &NODE ID='{nid}' or correct the DUCT NODE_ID reference.",
                        fix=_fix,
                    ))
        return results


class HvacTopologyRule:
    """The HVAC network is connected and has an ambient or vent node."""
    name = "HvacTopology"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        if not p.hvac_nodes and not p.hvac_ducts:
            return results

        node_ids = {n.name for n in p.hvac_nodes}
        duct_ids = {d.name for d in p.hvac_ducts}
        fan_duct_ids = {f.duct_id for f in p.fans if f.duct_id}
        damper_duct_ids = {d.duct_id for d in p.dampers if d.duct_id}

        # Every duct must reference two defined nodes
        for duct in p.hvac_ducts:
            for nid, side in [(duct.node_id_1, "NODE_ID(1)"),
                               (duct.node_id_2, "NODE_ID(2)")]:
                if nid and nid not in node_ids:
                    results.append(_e(self.name,
                        f"DUCT '{duct.name}' {side}='{nid}' references an undefined NODE.",
                        entity=duct.name,
                        hint=f"Define &NODE ID='{nid}' or correct the NODE_ID reference."))

        # Fan must reference a defined duct
        for fan in p.fans:
            if fan.duct_id and fan.duct_id not in duct_ids:
                results.append(_e(self.name,
                    f"FAN '{fan.name}' DUCT_ID='{fan.duct_id}' references an undefined DUCT.",
                    entity=fan.name))

        # Damper must reference a defined duct
        for damper in p.dampers:
            if damper.duct_id and damper.duct_id not in duct_ids:
                results.append(_e(self.name,
                    f"DAMPER '{damper.name}' DUCT_ID='{damper.duct_id}' references an undefined DUCT.",
                    entity=damper.name))

        # Check connectivity: all non-ambient nodes must be reachable from an ambient node
        # Build adjacency from ducts
        if p.hvac_nodes and p.hvac_ducts:
            ambient_nodes = {n.name for n in p.hvac_nodes if n.ambient}
            if not ambient_nodes:
                def _fix_ambient(project):
                    # Mark the first node as ambient if none are set
                    if project.hvac_nodes and not project.hvac_nodes[0].ambient:
                        project.hvac_nodes[0].ambient = True
                results.append(ValidationResult(
                    severity=Severity.WARNING,
                    rule=self.name,
                    message="HVAC network has no AMBIENT node. At least one &NODE AMBIENT=.TRUE. is required.",
                    hint="FDS needs an ambient boundary condition to solve the HVAC pressure network.",
                    fix=_fix_ambient,
                ))
            else:
                # BFS reachability from any ambient node
                adj: Dict[str, Set[str]] = {n.name: set() for n in p.hvac_nodes}
                for duct in p.hvac_ducts:
                    n1, n2 = duct.node_id_1, duct.node_id_2
                    if n1 in adj and n2 in adj:
                        adj[n1].add(n2)
                        adj[n2].add(n1)
                visited: Set[str] = set()
                queue = list(ambient_nodes & set(adj.keys()))
                while queue:
                    cur = queue.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    queue.extend(adj[cur] - visited)
                isolated = {n.name for n in p.hvac_nodes
                            if not n.ambient and n.name not in visited}
                for nid in sorted(isolated):
                    results.append(_w(self.name,
                        f"NODE '{nid}' is not connected to any ambient node through the duct network.",
                        entity=nid,
                        hint="Every non-ambient HVAC node must be reachable from an ambient boundary."))

        return results
