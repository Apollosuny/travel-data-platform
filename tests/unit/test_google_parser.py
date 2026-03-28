from travel_data_platform.providers.google_flights.parser import parse_offers


def test_parse_offers():
    raw_offers = [
        {
            "price": 2350000,
            "currency": "VND",
            "airline": "VietJet Air",
            "stops": 0,
        }
    ]

    offers = parse_offers(raw_offers)

    assert len(offers) == 1
    assert offers[0].price == 2350000
    assert offers[0].currency == "VND"
    assert offers[0].airline == "VietJet Air"