from evaluation.metrics import parse_tripinfo, summarize_step_csv

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


def test_summarize_step_csv(tmp_path):
    path = tmp_path / "steps.csv"
    path.write_text(STEP_CSV)
    summary = summarize_step_csv(str(path))
    assert summary["steps"] == 3
    assert summary["arrived_vehicles"] == 12
    assert summary["mean_step_waiting_time_s"] == 50.0
    assert summary["mean_speed_m_s"] == 6.0
