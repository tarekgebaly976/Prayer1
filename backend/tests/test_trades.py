"""Trades (crafts): default list plus trades already used in the plant; a welder is a Technician with trade Welder."""


def test_trade_list_and_people_with_new_trades(world):
    admin = world.api("admin")
    trades = admin.ok("get", "/trades")
    assert {"Machinist", "Welder", "Fitter", "Rigger"} <= set(trades)
    u = admin.ok(
        "post",
        "/users",
        {"email": "weld1@example.com", "full_name": "Ali Welder", "password": "Welder-Passw0rd!", "role": "technician", "trade": "Welder"},
        status=201,
    )
    assert u["user"]["trade"] == "Welder" and u["role_code"] == "technician"
    # A trade typed by the plant joins the list (no duplicates by case).
    admin.ok("patch", f"/users/{u['user']['id']}", {"trade": "Boiler maker"})
    admin.ok("patch", f"/users/{world.users['tech'].id}", {"trade": "welder"})
    trades = admin.ok("get", "/trades")
    assert "Boiler maker" in trades and sum(t.casefold() == "welder" for t in trades) == 1
    assert world.api("tech").get("/trades").status_code == 200  # everyone may read the list


def test_pm_import_trade_codes(world):
    from app.services.pm_import import _plan_code

    assert _plan_code("WS-LATHE-01", "M", "Machinist") == "WS-LATHE-01-M-MACH"
    assert _plan_code("WS-WELD-02", "Q", "Welder") == "WS-WELD-02-Q-WELD"
