"""Resolução de magistrado: órgão oficial → nome+tribunal → quarantine."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from src.connectors.cnj.compensation.courts import court_or_unknown
from src.models.compensation.canonical import Magistrate
from src.models.compensation.names import normalize_person_name
from src.pipelines.cnj.compensation.quarantine import make_quarantine

SOURCE_ID = "cnj_magistrate_compensation"


def _hash_id(*parts: str) -> str:
    basis = "|".join(parts)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def resolve_magistrates(compensations: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Nunca consolida homônimos automaticamente só pelo nome.
    Identificador do órgão + nome normalizado + tribunal.
    Ambiguidade intra-tribunal sem identificador → AMBIGUOUS_MAGISTRATE.
    """
    quarantine: list[dict] = []
    magistrates: dict[str, dict] = {}

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in compensations:
        court_id = row.get("court_id") or "unknown"
        name = normalize_person_name(row.get("normalized_name") or row.get("display_name") or "")
        grouped[(court_id, name)].append(row)

    for (court_id, name), rows in grouped.items():
        court = court_or_unknown(court_id)
        if court_id not in ("unknown", None) and court is None:
            quarantine.append(
                make_quarantine(
                    "UNKNOWN_COURT",
                    payload={"court_id": court_id, "name": name},
                    entity_hint=name,
                )
            )

        idents = {(r.get("source_person_identifier") or "").strip() for r in rows}
        idents.discard("")
        positions = {(r.get("position") or "").strip() for r in rows}
        positions.discard("")

        if len(idents) > 1:
            # Mesmo nome no mesmo tribunal com identificadores distintos: pessoas distintas.
            for ident in sorted(idents):
                subset = [r for r in rows if (r.get("source_person_identifier") or "").strip() == ident]
                mag_id = f"mag_{court_id}_{_hash_id(court_id, ident)}"
                pos = next((r.get("position") for r in subset if r.get("position")), None)
                mag = Magistrate(
                    magistrate_id=mag_id,
                    normalized_name=name,
                    court_id=court_id,
                    position=pos,
                    source_id=SOURCE_ID,
                    source_person_identifier=ident,
                    display_name=next((r.get("display_name") for r in subset if r.get("display_name")), None),
                    resolution_method="court_official_identifier",
                    resolution_confidence="high",
                )
                magistrates[mag_id] = mag.to_dict()
                for r in subset:
                    r["magistrate_id"] = mag_id
                    r["resolution_method"] = mag.resolution_method
            # linhas sem ident no mesmo grupo
            leftover = [r for r in rows if not (r.get("source_person_identifier") or "").strip()]
            if leftover:
                qid = f"mag_q_{court_id}_{_hash_id(court_id, name, 'ambiguous')}"
                quarantine.append(
                    make_quarantine(
                        "AMBIGUOUS_MAGISTRATE",
                        payload={
                            "court_id": court_id,
                            "normalized_name": name,
                            "reason": "mesmo nome no tribunal com identificadores mistos e linhas sem id",
                            "rows": len(leftover),
                        },
                        entity_hint=name,
                    )
                )
                for r in leftover:
                    r["magistrate_id"] = qid
                    r["resolution_method"] = "quarantine_provisional"
            continue

        if len(idents) == 1:
            ident = next(iter(idents))
            mag_id = f"mag_{court_id}_{_hash_id(court_id, ident)}"
            method = "court_official_identifier"
            confidence = "high"
        else:
            # Só nome + tribunal. Se há cargos muito distintos no mesmo mês, quarentena.
            if len(positions) > 1:
                mag_id = f"mag_q_{court_id}_{_hash_id(court_id, name)}"
                method = "name_court_quarantine"
                confidence = "low"
                quarantine.append(
                    make_quarantine(
                        "AMBIGUOUS_MAGISTRATE",
                        payload={
                            "court_id": court_id,
                            "normalized_name": name,
                            "positions": sorted(positions),
                            "reason": "homônimo potencial: mesmo nome, sem identificador, cargos distintos",
                        },
                        entity_hint=name,
                    )
                )
            else:
                mag_id = f"mag_{court_id}_{_hash_id(court_id, name)}"
                method = "normalized_name_and_court"
                confidence = "medium"

        pos = next((r.get("position") for r in rows if r.get("position")), None)
        ident = next(iter(idents), None)
        mag = Magistrate(
            magistrate_id=mag_id,
            normalized_name=name,
            court_id=court_id,
            position=pos,
            source_id=SOURCE_ID,
            source_person_identifier=ident,
            display_name=next((r.get("display_name") for r in rows if r.get("display_name")), None),
            resolution_method=method,
            resolution_confidence=confidence,
        )
        magistrates[mag_id] = mag.to_dict()
        for r in rows:
            r["magistrate_id"] = mag_id
            r["resolution_method"] = method

    # Recalcula id estável da remuneração agora com magistrate_id
    for row in compensations:
        if not row.get("magistrate_id"):
            row["magistrate_id"] = f"mag_q_unknown_{_hash_id(row.get('row_key') or '')}"
            quarantine.append(
                make_quarantine(
                    "AMBIGUOUS_MAGISTRATE",
                    payload={"row_key": row.get("row_key")},
                    entity_hint=row.get("normalized_name"),
                )
            )

    return {
        "magistrates": list(magistrates.values()),
        "compensations": compensations,
        "quarantine": quarantine,
    }
