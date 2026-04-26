from models import Role


def test_member_create_and_update_qualified_roles(client, db_session):
    worship_role = Role(role_name="Worship Leader", people_needed=2, same_gender_required=True)
    av_role = Role(role_name="AV Operator", people_needed=1, same_gender_required=False)
    db_session.add_all([worship_role, av_role])
    db_session.commit()
    db_session.refresh(worship_role)
    db_session.refresh(av_role)

    create_response = client.post(
        "/api/v1/members",
        json={
            "member_name": "Test Member",
            "member_gender": "female",
            "email": "test.member@example.com",
            "phone": "123-456-7890",
            "bible_study_group": "group_a",
            "is_senior_for_pairing": False,
            "qualified_roles": [worship_role.role_id, av_role.role_id],
        },
    )

    assert create_response.status_code == 201
    member = create_response.json()

    member_details = client.get(f"/api/v1/members/{member['member_id']}")
    assert member_details.status_code == 200
    detail_body = member_details.json()
    assert detail_body["member_name"] == "Test Member"
    assert {role["role_name"] for role in detail_body["roles"]} == {"Worship Leader", "AV Operator"}

    update_response = client.put(
        f"/api/v1/members/{member['member_id']}",
        json={
            "bible_study_group": "group_b",
            "is_senior_for_pairing": True,
            "qualified_roles": [av_role.role_id],
        },
    )

    assert update_response.status_code == 200

    updated_details = client.get(f"/api/v1/members/{member['member_id']}")
    assert updated_details.status_code == 200
    updated_body = updated_details.json()
    assert updated_body["bible_study_group"] == "group_b"
    assert updated_body["is_senior_for_pairing"] is True
    assert [role["role_name"] for role in updated_body["roles"]] == ["AV Operator"]

    clear_roles_response = client.put(
        f"/api/v1/members/{member['member_id']}",
        json={"qualified_roles": []},
    )

    assert clear_roles_response.status_code == 200

    cleared_details = client.get(f"/api/v1/members/{member['member_id']}")
    assert cleared_details.status_code == 200
    assert cleared_details.json()["roles"] == []
