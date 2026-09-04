from frontend.application.services import risks_from_assessment


def test_synthetic_result_is_presented_as_demo_target() -> None:
    assessment = {
        "prediction": [
            {
                "outcome": {"text": "fall"},
                "probabilityDecimal": 0.25,
                "extension": [
                    {
                        "url": "https://example.test/risk-status",
                        "valueCode": "synthetic-demo-result",
                    }
                ],
            }
        ]
    }

    result = risks_from_assessment(assessment)[0]

    assert result.label == "Demo-Ziel: Sturzereignis"
    assert result.status == "synthetic-demo-result"
