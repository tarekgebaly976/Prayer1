from tests.conftest import login

NEW_PW = "Fresh-Passw0rd!2026"


def test_edit_reset_password_remove_and_readd_user(world):
    admin = world.api("admin")
    u = admin.ok(
        "post",
        "/users",
        {"email": "m.awaji@example.com", "full_name": "Mohamed Awaji", "password": "Start-Passw0rd!26", "role": "planner"},
        status=201,
    )
    uid = u["user"]["id"]
    # Fix a typo in the e-mail and name, and change the role.
    r = admin.ok("patch", f"/users/{uid}", {"email": "m.awaji2@example.com", "full_name": "Mohamed Awaji (Planning)", "role": "engineer"})
    assert r["user"]["email"] == "m.awaji2@example.com" and r["role_code"] == "engineer"
    taken = admin.patch(f"/users/{uid}", {"email": "tech@example.com"})
    assert taken.status_code == 409

    # Forgotten password: admin sets a temporary one; old sessions end.
    session = login("m.awaji2@example.com", world.plant.id, "Start-Passw0rd!26")
    assert admin.post(f"/users/{uid}/reset-password", {"password": "weak"}).status_code == 422
    admin.ok("post", f"/users/{uid}/reset-password", {"password": NEW_PW}, status=204)
    assert session.get("/auth/me").status_code == 401
    login("m.awaji2@example.com", world.plant.id, NEW_PW)

    # Remove from the plant, then add again with the same e-mail.
    assert world.api("planner").delete(f"/users/{uid}").status_code == 403  # needs user.manage
    assert admin.delete(f"/users/{world.users['admin'].id}").status_code == 409  # not yourself
    admin.ok("delete", f"/users/{uid}", status=204)
    assert uid not in {m["user"]["id"] for m in admin.get("/users").json()}
    again = admin.ok(
        "post",
        "/users",
        {"email": "m.awaji2@example.com", "full_name": "Mohamed Awaji", "password": "Again-Passw0rd!26", "role": "planner"},
        status=201,
    )
    assert again["user"]["id"] == uid and again["role_code"] == "planner"  # same person: history stays linked
    login("m.awaji2@example.com", world.plant.id, "Again-Passw0rd!26")


def test_plant_admin_cannot_touch_system_admin(world):
    manager = world.api("manager")  # has everything except plant.admin / user.manage
    assert manager.post(f"/users/{world.users['admin'].id}/reset-password", {"password": NEW_PW}).status_code == 403
