from evaluation.metrics import parse_tripinfo, summarize_evs, summarize_step_csv

TRIPINFO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<tripinfos>
    <tripinfo id="v0" depart="0" arrival="10" duration="10" routeLength="100" waitingTime="2" timeLoss="3"/>
    <tripinfo id="v1" depart="0" arrival="20" duration="20" routeLength="200" waitingTime="4" timeLoss="6"/>
</tripinfos>
"""

STEP_CSV = (
    "step,active_vehicles,arrived_vehicles,avg_speed_m_s,total_waiting_time_s,co2_mg_s,fuel_ml_s\n"
    "1,10,0,5.0,100.0,0,0\n"
    "2,0,10,0.0,0.0,0,0\n"
    "3,5,2,7.0,50.0,0,0\n"
)


def test_parse_tripinfo(tmp_path):
    path = tmp_path / "tripinfo.xml"
    path.write_text(TRIPINFO_XML)
    result = parse_tripinfo(str(path))
    assert result["summary"]["arrived_vehicles"] == 2
    assert result["summary"]["mean_duration_s"] == 15.0
    assert result["summary"]["mean_tripinfo_waiting_s"] == 3.0
    assert result["summary"]["mean_time_loss_s"] == 4.5
    assert len(result["vehicles"]) == 2


def test_parse_tripinfo_empty(tmp_path):
    path = tmp_path / "tripinfo.xml"
    path.write_text('<?xml version="1.0"?><tripinfos></tripinfos>')
    result = parse_tripinfo(str(path))
    assert result["summary"]["arrived_vehicles"] == 0
    assert result["summary"]["mean_duration_s"] == 0.0


MIXED_TRIPINFO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<tripinfos>
    <tripinfo id="veh_0" depart="0" arrival="20" duration="20" routeLength="200" waitingTime="4" waitingCount="1" timeLoss="6"/>
    <tripinfo id="ev_0" depart="0" arrival="30" duration="30" routeLength="300" waitingTime="1" waitingCount="0" timeLoss="2"/>
    <tripinfo id="ev_1" depart="0" arrival="50" duration="50" routeLength="300" waitingTime="3" waitingCount="2" timeLoss="5"/>
    <tripinfo id="incident_B1B2_0" depart="0" arrival="400" duration="400" routeLength="10" waitingTime="395" waitingCount="1" timeLoss="395"/>
</tripinfos>
"""


def test_parse_tripinfo_excludes_evs_and_blockers(tmp_path):
    path = tmp_path / "tripinfo.xml"
    path.write_text(MIXED_TRIPINFO_XML)
    result = parse_tripinfo(str(path))
    assert result["summary"]["vehicles_total"] == 4
    assert result["summary"]["arrived_vehicles"] == 1
    assert result["summary"]["mean_duration_s"] == 20.0
    assert len(result["vehicles"]) == 4


def test_summarize_evs(tmp_path):
    path = tmp_path / "tripinfo.xml"
    path.write_text(MIXED_TRIPINFO_XML)
    result = parse_tripinfo(str(path))
    ev = summarize_evs(result["vehicles"])
    assert ev["ev_count"] == 2
    assert ev["ev_mean_duration_s"] == 40.0
    assert ev["ev_mean_waiting_s"] == 2.0
    assert ev["ev_mean_waiting_count"] == 1.0
    assert ev["ev_max_duration_s"] == 50.0


def test_summarize_step_csv(tmp_path):
    path = tmp_path / "steps.csv"
    path.write_text(STEP_CSV)
    summary = summarize_step_csv(str(path))
    assert summary["steps"] == 3
    assert summary["arrived_vehicles"] == 12
    assert summary["mean_step_waiting_time_s"] == 50.0
    assert summary["mean_speed_m_s"] == 6.0
