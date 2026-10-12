"""ResultIndex: scanning a results folder and ingesting a .smv."""
from __future__ import annotations

from typing import TYPE_CHECKING

import logging
from pathlib import Path
from typing import Optional

from .reader import DeviceReader, LogParser

from .indexer_boundary import (
    BoundaryIndex,
    BoundaryIndexEntry,
    DeviceFile,
)
from .indexer_slices import SliceIndex, SliceIndexEntry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .indexer import ResultIndex


class ResultIndexBuildMixin:
    @classmethod
    def build(
        cls,
        output_dir: str,
        chid: Optional[str] = None,
        *,
        index_slices: bool = True,
        index_boundaries: bool = True,
        index_plot3d: bool = True,
        index_particles: bool = True,
        use_smv: bool = True,
    ) -> "ResultIndex":
        """
        Build a full index for *output_dir*.

        When *use_smv* is True (default) and a ``.smv`` file is found in
        *output_dir*, the SMV file is used as the primary source of output-file
        metadata instead of reading each binary header individually.  Binary
        header reads are still performed for any files not listed in the SMV.

        Parameters
        ----------
        output_dir : str
            Directory containing FDS output files.
        chid : str, optional
            Case ID; if omitted, inferred from the ``.smv`` or ``.out`` file.
        index_slices : bool
            Whether to scan and index ``*.sf`` files.
        index_boundaries : bool
            Whether to scan and index ``*.bf`` files.
        index_plot3d : bool
            Whether to scan and record ``*.q`` Plot3D file paths.
        index_particles : bool
            Whether to scan and record ``*.prt5`` particle file paths.
        use_smv : bool
            Use the ``.smv`` file as the primary metadata source when present.
        """
        idx = cls()
        idx.output_dir = str(output_dir)
        dir_path = Path(output_dir)

        # ── Try SMV-first path ────────────────────────────────────────────────
        smv_files = sorted(dir_path.glob("*.smv"))
        smv_path = smv_files[0] if smv_files else None

        if use_smv and smv_path:
            try:
                idx._ingest_smv(smv_path, dir_path)
                if chid:
                    idx.chid = chid
                elif idx.chid:
                    pass  # from SMV
                logger.info("ResultIndex: SMV-enhanced build from %s", smv_path.name)
            except Exception as exc:
                logger.warning("ResultIndex: SMV parse failed (%s), falling back", exc)
                smv_path = None  # fall through to directory scan

        # ── Infer CHID from .out / directory name if still unknown ───────────
        if not idx.chid:
            if chid:
                idx.chid = chid
            else:
                out_files = list(dir_path.glob("*.out"))
                idx.chid = out_files[0].stem if out_files else dir_path.name

        logger.info("ResultIndex.build: scanning %s (chid=%s)", output_dir, idx.chid)

        # ── Parse .out log ────────────────────────────────────────────────────
        out_path = dir_path / f"{idx.chid}.out"
        if out_path.exists():
            idx.stats = LogParser().parse(str(out_path))
        else:
            for p in dir_path.glob("*.out"):
                try:
                    idx.stats = LogParser().parse(str(p))
                except Exception:
                    pass
                break

        # ── Index device CSVs ─────────────────────────────────────────────────
        devc_reader = DeviceReader()
        for csv_path in sorted(dir_path.glob("*_devc.csv")):
            try:
                results = devc_reader.read(str(csv_path))
                names = [k for k in results.keys() if k.lower() != "time"]
                case_chid = csv_path.stem.replace("_devc", "")
                idx.device_files.append(DeviceFile(
                    filepath=str(csv_path),
                    chid=case_chid,
                    device_names=names,
                ))
                logger.debug("ResultIndex: %d devices from %s", len(names), csv_path.name)
            except Exception as exc:
                logger.warning("ResultIndex: skipping device CSV %s: %s", csv_path.name, exc)

        # ── Slice / boundary / Plot3D / particle indexing ─────────────────────
        # When the SMV already populated these, skip binary re-scan for known
        # files; still pick up any additional files not in the SMV listing.
        smv_sf_paths  = {e.filepath for e in idx.slice_index.all_entries()}
        smv_bf_paths  = {e.filepath for e in idx.boundary_index.all_entries()}
        smv_q_paths   = set(idx.plot3d_files)
        smv_prt_paths = set(idx.particle_files)

        if index_slices:
            extra_sf = [
                f for f in sorted(dir_path.glob("*.sf"))
                if str(f) not in smv_sf_paths
            ]
            if extra_sf:
                extra_idx = SliceIndex()
                extra_idx._scan_files(extra_sf)
                idx.slice_index._entries.extend(extra_idx._entries)
            if not smv_sf_paths:
                idx.slice_index = SliceIndex.build(output_dir)

        if index_boundaries:
            extra_bf = [
                f for f in sorted(dir_path.glob("*.bf"))
                if str(f) not in smv_bf_paths
            ]
            if extra_bf:
                extra_bidx = BoundaryIndex()
                extra_bidx._scan_files(extra_bf)
                idx.boundary_index._entries.extend(extra_bidx._entries)
            if not smv_bf_paths:
                idx.boundary_index = BoundaryIndex.build(output_dir)

        if index_plot3d:
            for q_path in sorted(dir_path.glob("*.q")):
                if str(q_path) not in smv_q_paths:
                    idx.plot3d_files.append(str(q_path))
                    logger.debug("ResultIndex: found extra Plot3D %s", q_path.name)

        if index_particles:
            for prt_path in sorted(dir_path.glob("*.prt5")):
                if str(prt_path) not in smv_prt_paths:
                    idx.particle_files.append(str(prt_path))
                    logger.debug("ResultIndex: found extra particle %s", prt_path.name)

        logger.info(
            "ResultIndex built: slices=%d  boundaries=%d  devc_files=%d  "
            "plot3d=%d  particles=%d  completed=%s  smv=%s",
            len(idx.slice_index), len(idx.boundary_index),
            len(idx.device_files), len(idx.plot3d_files),
            len(idx.particle_files), idx.stats.completed,
            bool(idx.smv_filepath),
        )
        return idx

    @classmethod
    def build_from_smv(cls, smv_filepath: str) -> "ResultIndex":
        """
        Build an index directly from a ``.smv`` file.

        The output directory is inferred from the SMV file's parent directory.
        This is the fastest build path when a ``.smv`` file is available: no
        binary header reads are performed.

        Parameters
        ----------
        smv_filepath : str
            Absolute or relative path to the ``.smv`` file.
        """
        smv_path = Path(smv_filepath)
        idx = cls()
        idx.output_dir = str(smv_path.parent)
        idx._ingest_smv(smv_path, smv_path.parent)

        # Parse .out log
        out_path = smv_path.parent / f"{idx.chid}.out"
        if out_path.exists():
            idx.stats = LogParser().parse(str(out_path))
        else:
            for p in smv_path.parent.glob("*.out"):
                try:
                    idx.stats = LogParser().parse(str(p))
                except Exception:
                    pass
                break

        # Index device CSVs
        devc_reader = DeviceReader()
        for csv_path in sorted(smv_path.parent.glob("*_devc.csv")):
            try:
                results = devc_reader.read(str(csv_path))
                names = [k for k in results.keys() if k.lower() != "time"]
                idx.device_files.append(DeviceFile(
                    filepath=str(csv_path),
                    chid=csv_path.stem.replace("_devc", ""),
                    device_names=names,
                ))
            except Exception as exc:
                logger.warning("ResultIndex: skipping %s: %s", csv_path.name, exc)

        logger.info("ResultIndex.build_from_smv: %s  grids=%d  slices=%d",
                    smv_path.name, len(idx.smv_grids), len(idx.slice_index))
        return idx

    def _ingest_smv(self, smv_path: Path, base_dir: Path) -> None:
        """Populate index fields from a parsed SMV file."""
        from pyfds.results.smv_parser import SmvParser
        meta = SmvParser().parse(str(smv_path))
        self.smv_metadata = meta
        self.smv_filepath = str(smv_path)
        self.chid = meta.chid or smv_path.stem
        self.smv_grids = list(meta.grids)

        # Device locations
        for dev in meta.devices:
            self.smv_devices[dev.name] = dev

        # Slice entries from SMV (no binary header read)
        for slc in meta.slices:
            fp = str(base_dir / slc.filepath) if not Path(slc.filepath).is_absolute() else slc.filepath
            self.slice_index._entries.append(SliceIndexEntry(
                filepath=fp,
                quantity=slc.quantity,
                short_name=slc.short_name,
                units=slc.units,
                mesh_id=slc.mesh_id,
                i1=slc.i1, i2=slc.i2,
                j1=slc.j1, j2=slc.j2,
                k1=slc.k1, k2=slc.k2,
            ))

        # Boundary entries from SMV
        for bndf in meta.boundaries:
            fp = str(base_dir / bndf.filepath) if not Path(bndf.filepath).is_absolute() else bndf.filepath
            self.boundary_index._entries.append(BoundaryIndexEntry(
                filepath=fp,
                quantity=bndf.quantity,
                short_name=bndf.short_name,
                units=bndf.units,
                mesh_id=bndf.mesh_id,
                n_patches=0,   # SMV doesn't give patch count; read lazily
            ))

        # Plot3D paths from SMV
        for pl in meta.plot3d:
            fp = str(base_dir / pl.filepath) if not Path(pl.filepath).is_absolute() else pl.filepath
            self.plot3d_files.append(fp)

        # Particle paths from SMV
        for prt in meta.particles:
            fp = str(base_dir / prt.filepath) if not Path(prt.filepath).is_absolute() else prt.filepath
            self.particle_files.append(fp)
