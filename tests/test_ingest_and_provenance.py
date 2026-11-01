import h5py
import numpy as np
import pandas as pd
import pytest

from rb import provenance
from rb.graph import export_graph
from rb.ingest.pipeline import IngestError, ingest_file
from rb.models import ProvenanceRecord


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "trasporto.csv"
    pd.DataFrame({"T (K)": np.linspace(10, 300, 50), "R [ohm]": np.linspace(1, 5, 50), "campione": ["A"] * 50}).to_csv(path, index=False)
    return path


@pytest.fixture
def h5_file(tmp_path):
    path = tmp_path / "scan.nxs"
    with h5py.File(path, "w") as f:
        f.attrs["instrument"] = "diffrattometro"
        g = f.create_group("entry/data")
        d = g.create_dataset("temperature", data=np.linspace(5, 50, 100))
        d.attrs["units"] = "K"
        g.create_dataset("counts", data=np.arange(100))
    return path


@pytest.fixture
def pdf_file(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "paper.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(72, 760, "Superconductivity in thin films")
    c.drawString(72, 740, "We report T_c = 39.2 +/- 0.3 K at a field of 10 mT.")
    c.drawString(72, 720, "See doi 10.1103/PhysRevB.64.020501 and arXiv:2101.01234v2.")
    c.save()
    return path


def test_csv_ingest_creates_variables_with_units(session, project, csv_file, settings):
    summary = ingest_file(session, project.id, csv_file, storage_dir=settings.storage_dir)
    assert summary["created"]["variables"] == 3
    g = export_graph(session, project.id)
    temp = next(n for n in g["nodes"] if n["type"] == "variable" and n["label"] == "T")
    assert temp["props"]["unit"] == "K" and temp["props"]["dimensionality"] == "[temperature]"


def test_hdf5_ingest_reads_units_attribute(session, project, h5_file, settings):
    summary = ingest_file(session, project.id, h5_file, storage_dir=settings.storage_dir, classification="confidential")
    assert summary["kind"] == "dataset" and summary["created"]["variables"] == 2
    g = export_graph(session, project.id)
    temp = next(n for n in g["nodes"] if n["label"] == "temperature")
    assert temp["props"]["path"] == "/entry/data/temperature"
    assert temp["props"]["stats"]["max"] == pytest.approx(50)


def test_pdf_ingest_extracts_references_quantities_and_links(session, project, pdf_file, csv_file, settings):
    ingest_file(session, project.id, csv_file, storage_dir=settings.storage_dir)
    summary = ingest_file(session, project.id, pdf_file, storage_dir=settings.storage_dir)
    assert summary["created"]["references"] == 2
    assert summary["created"]["quantities"] >= 2
    # T_c (temperatura) del paper collegata alla variabile T (K) del dataset
    assert summary["created"]["links"] >= 1
    labels = {n["label"] for n in export_graph(session, project.id)["nodes"]}
    assert "doi:10.1103/PhysRevB.64.020501" in labels and "arxiv:2101.01234" in labels


def test_duplicate_file_is_not_ingested_twice(session, project, csv_file, settings):
    ingest_file(session, project.id, csv_file, storage_dir=settings.storage_dir)
    assert ingest_file(session, project.id, csv_file, storage_dir=settings.storage_dir)["duplicate"] is True


def test_invalid_classification_rejected(session, project, csv_file, settings):
    with pytest.raises(IngestError):
        ingest_file(session, project.id, csv_file, storage_dir=settings.storage_dir, classification="segreto")


def test_provenance_chain_detects_tampering(session, project, csv_file, h5_file, settings):
    ingest_file(session, project.id, csv_file, storage_dir=settings.storage_dir)
    ingest_file(session, project.id, h5_file, storage_dir=settings.storage_dir)
    assert provenance.verify_chain(session, project.id) == (True, None)
    first = session.query(ProvenanceRecord).order_by(ProvenanceRecord.id).first()
    first.params = {"classification": "public"}  # manomissione
    session.flush()
    ok, broken = provenance.verify_chain(session, project.id)
    assert not ok and broken == first.id
