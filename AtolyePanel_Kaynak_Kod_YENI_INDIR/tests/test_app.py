import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
import app as site


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(site, 'DB_FILE', tmp_path/'test.sqlite3')
    site.demo_seed()
    with TestClient(site.app) as c:
        yield c


def csrf(page):
    token = re.search(r'name="csrf" value="([^"]+)"', page.text)
    assert token, page.text[:400]
    return token.group(1)


def enter(client, username='admin', password='DemoAdmin123!'):
    page = client.get('/login')
    response = client.post('/login', data={'csrf':csrf(page),'username':username,'password':password}, follow_redirects=True)
    assert 'Bakım Kartı Takip Panosu' in response.text
    return csrf(response)


def test_requires_login(client):
    response=client.get('/dashboard', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location']=='/login'


def test_admin_create_card_and_technician_update(client):
    admin_token=enter(client)
    response=client.post('/cards/new', data={'csrf':admin_token,'aircraft_id':1,'card_code':'UT-989',
            'title':'Deneme UT kartı','planned_date':'2026-11-04','planned_time':'10:40',
            'workshop':'ISL1'}, follow_redirects=False)
    assert response.status_code == 303
    url=response.headers['location']
    assert 'cards/' in url
    assert 'Deneme UT kartı' in client.get(url).text
    client.post('/logout',data={'csrf':admin_token})
    tech_token=enter(client,'teknisyen','DemoTek123!')
    assert client.get('/cards/new').status_code == 403
    assert client.get('/users').status_code == 403
    response=client.post('/cards/new',data={'csrf':tech_token,'aircraft_id':1,'card_code':'HACK',
            'title':'No','planned_date':'2026-11-04'},follow_redirects=False)
    assert response.status_code == 403
    response=client.post(url+'/update',data={'csrf':tech_token,'status':'in_progress',
        'actual_received_at':datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m-%dT%H:%M'),
        'note':'Parça geldi, kontrol başlıyor.'},follow_redirects=True)
    assert response.status_code == 200
    assert 'Parça geldi, kontrol başlıyor.' in response.text
    with site.conn() as db:
        card_id=int(url.rsplit('/',1)[1])
        row=db.execute('SELECT status,actual_received_at,latest_note FROM cards WHERE id=?',(card_id,)).fetchone()
        history=db.execute('SELECT count(*) FROM card_events WHERE card_id=?',(card_id,)).fetchone()[0]
    assert row['status']=='in_progress' and row['actual_received_at']
    assert history == 3  # creation + automatic ownership + status update
    response=client.post(url+'/update',data={'csrf':tech_token,'status':'completed',
        'actual_received_at':(datetime.now(ZoneInfo('Europe/Istanbul')).replace(day=1)).strftime('%Y-%m-%dT%H:%M'),
        'note':'Düzeltme denemesi'},follow_redirects=True)
    assert 'yalnızca yönetici' in response.text


def test_csrf_and_export(client):
    token=enter(client)
    response=client.post('/aircraft',data={'csrf':'WRONG','registration':'NOPE'},follow_redirects=False)
    assert response.status_code==403
    response=client.get('/export.csv')
    assert response.status_code == 200
    assert 'text/csv' in response.headers['content-type']
    assert 'DEMO-001' in response.text


def test_last_admin_cannot_deactivate_self(client):
    token=enter(client)
    response=client.post('/users/1/toggle',data={'csrf':token},follow_redirects=True)
    assert 'Kendi hesabınızı pasifleştiremezsiniz' in response.text


def test_demo_cards_exhibit_overdue(client):
    enter(client)
    page=client.get('/dashboard')
    assert 'Gecikti' in page.text
    assert 'NDT-UT-101' in page.text


def test_technician_can_complete_and_comment_and_admin_reset_password(client):
    admin = enter(client)
    response = client.post('/users',data={'csrf':admin,'username':'bakim.test','full_name':'Bakım Test',
        'password':'StrongTest123!','role':'technician'}, follow_redirects=True)
    assert 'Bakım Test' in response.text
    with site.conn() as db:
        user_id=db.execute("SELECT id FROM users WHERE username='bakim.test'").fetchone()['id']
    response=client.post(f'/users/{user_id}/reset-password', data={'csrf':admin,'new_password':'AnotherTest123!'},follow_redirects=True)
    assert 'Kullanıcı parolası yenilendi' in response.text
    client.post('/logout',data={'csrf':admin})
    technician=enter(client,'bakim.test','AnotherTest123!')
    with site.conn() as db:
        card_id=db.execute('SELECT id FROM cards WHERE actual_received_at IS NULL LIMIT 1').fetchone()['id']
    start=datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m-%dT%H:%M')
    result=client.post(f'/cards/{card_id}/update',data={'csrf':technician,'status':'completed',
        'actual_received_at':start,'actual_completed_at':start,'note':'İşlem tamamlandı, sonuç kaydı eklendi.'},follow_redirects=True)
    assert result.status_code == 200
    assert 'İşlem tamamlandı, sonuç kaydı eklendi.' in result.text
    with site.conn() as db:
        row=db.execute('SELECT actual_completed_at,status FROM cards WHERE id=?',(card_id,)).fetchone()
    assert row['actual_completed_at'] and row['status']=='completed'
    result=client.post(f'/cards/{card_id}/update',data={'csrf':technician,'status':'completed',
        'note':'Kontrol notu eklendi.'},follow_redirects=True)
    assert 'Kontrol notu eklendi.' in result.text
    assert client.post(f'/users/{user_id}/reset-password',data={'csrf':technician,'new_password':'NoPermission123!'}).status_code==403


def create_tech(client, admin_csrf, username, name):
    response = client.post('/users', data={'csrf':admin_csrf, 'username':username,
        'full_name':name,'password':'TechPassword123!','role':'technician'},follow_redirects=True)
    assert response.status_code == 200
    with site.conn() as db:
        return db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()['id']


def test_admin_assigns_and_technician_has_personal_list(client):
    token=enter(client)
    other_id=create_tech(client,token,'teknisyen2','İkinci Teknisyen')
    response=client.post('/cards/new',data={'csrf':token,'aircraft_id':1,'card_code':'ASSIGN-9',
        'title':'Atamalı bakım kartı','planned_date':'2026-11-05','workshop':'ISL2','assigned_to':str(other_id)},follow_redirects=False)
    assert response.status_code==303
    cid=int(response.headers['location'].split('/')[-1])
    with site.conn() as db:
        row=db.execute('SELECT assigned_to FROM cards WHERE id=?',(cid,)).fetchone()
        audit=db.execute('SELECT event_type,to_assignee_id FROM card_events WHERE card_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone()
    assert row['assigned_to']==other_id
    assert audit['event_type']=='Sorumlu atandı' and audit['to_assignee_id']==other_id
    assert 'İkinci Teknisyen' in client.get('/dashboard').text
    client.post('/logout',data={'csrf':token})
    tech_csrf=enter(client,'teknisyen2','TechPassword123!')
    page=client.get('/my-tasks')
    assert 'ASSIGN-9' in page.text and 'Bana Atanan Kartlar' in page.text
    assert client.get('/assignments').status_code==200
    res=client.post(f'/cards/{cid}/update',data={'csrf':tech_csrf,'status':'on_hold',
        'note':'Ekipman yedeği bekleniyor.'},follow_redirects=True)
    assert 'Ekipman yedeği bekleniyor.' in res.text


def test_assignment_restrictions_and_shift_handover_audit(client):
    admin=enter(client)
    owner_id=create_tech(client,admin,'ilk','Birinci Teknisyen')
    next_id=create_tech(client,admin,'ikinci','İkinci Teknisyen')
    with site.conn() as db:
        cid=db.execute("SELECT id FROM cards WHERE card_code='NDT-UT-101'").fetchone()['id']
    url=f'/cards/{cid}'
    result=client.post(url+'/assign',data={'csrf':admin,'assignee_id':str(owner_id)},follow_redirects=True)
    assert 'Kart sorumlusu kaydedildi' in result.text
    result=client.post(url+'/assign',data={'csrf':admin,'assignee_id':str(next_id)},follow_redirects=True)
    assert 'gerekçe zorunludur' in result.text
    client.post('/logout',data={'csrf':admin})
    intruder=enter(client,'ikinci','TechPassword123!')
    assert 'Salt okunur kart' in client.get(url).text
    deny=client.post(url+'/update',data={'csrf':intruder,'status':'received','note':'İzinsiz güncelleme'},follow_redirects=False)
    assert deny.status_code==403
    deny=client.post(url+'/handover',data={'csrf':intruder,'to_user_id':str(owner_id),
        'shift_name':'Akşam','note':'Yetkisiz vardiya devri'},follow_redirects=False)
    assert deny.status_code==403
    client.post('/logout',data={'csrf':intruder})
    first=enter(client,'ilk','TechPassword123!')
    result=client.post(url+'/handover',data={'csrf':first,'to_user_id':str(next_id),
        'shift_name':'Akşam','note':'İşlem bekleniyor, aparat teslim edildi.'},follow_redirects=True)
    assert 'İkinci Teknisyen adlı teknisyene devredildi' in result.text
    assert 'İşlem bekleniyor, aparat teslim edildi.' in result.text
    assert 'Birinci Teknisyen → İkinci Teknisyen' in result.text
    with site.conn() as db:
        row=db.execute('SELECT assigned_to FROM cards WHERE id=?',(cid,)).fetchone()
        event=db.execute("SELECT * FROM card_events WHERE card_id=? AND event_type='Vardiya devri'",(cid,)).fetchone()
    assert row['assigned_to']==next_id
    assert event['from_assignee_id']==owner_id and event['to_assignee_id']==next_id
    assert event['shift_name']=='Akşam'
    assert 'NDT-UT-101' not in client.get('/my-tasks').text
    assert 'NDT-UT-101' in client.get('/assignments').text
    deny=client.post(url+'/update',data={'csrf':first,'status':'in_progress','note':'Devir sonrası izinsiz'},follow_redirects=False)
    assert deny.status_code==403


def test_claim_only_available_when_unassigned_and_owner_update(client):
    admin=enter(client)
    with site.conn() as db:
        cid=db.execute("SELECT id FROM cards WHERE card_code='NDT-UT-101'").fetchone()['id']
    client.post('/logout',data={'csrf':admin})
    tech=enter(client,'teknisyen','DemoTek123!')
    response=client.post(f'/cards/{cid}/claim',data={'csrf':tech},follow_redirects=True)
    assert 'Kart sorumluluğunu üstlendiniz' in response.text
    response=client.post(f'/cards/{cid}/claim',data={'csrf':tech},follow_redirects=True)
    assert 'Bu kart boşta değil' in response.text
    assert f'/cards/{cid}'
    with site.conn() as db:
        assert db.execute('SELECT count(*) FROM card_events WHERE card_id=? AND event_type=?',(cid,'Görev devralındı')).fetchone()[0]==1


def test_completed_card_cannot_be_handed_over(client):
    admin=enter(client)
    other_id=create_tech(client,admin,'ikinci','İkinci Teknisyen')
    with site.conn() as db:
        cid=db.execute("SELECT id FROM cards WHERE card_code='NDT-UT-101'").fetchone()['id']
    start=datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m-%dT%H:%M')
    client.post(f'/cards/{cid}/update',data={'csrf':admin,'status':'completed',
        'actual_received_at':start,'actual_completed_at':start,'note':'Test kapatma'},follow_redirects=True)
    result=client.post(f'/cards/{cid}/assign',data={'csrf':admin,'assignee_id':str(other_id)},follow_redirects=True)
    assert 'Tamamlanan kartın sorumlusu değiştirilemez' in result.text
    result=client.post(f'/cards/{cid}/handover',data={'csrf':admin,'to_user_id':str(other_id),
        'shift_name':'Sabah','note':'Test devri engelle'},follow_redirects=True)
    assert 'Tamamlanan kartlar devredilemez' in result.text


def test_note_author_not_overwritten_by_subsequent_assignment(client):
    admin=enter(client)
    other_id=create_tech(client,admin,'ikinci','İkinci Teknisyen')
    with site.conn() as db:
        cid=db.execute("SELECT id FROM cards WHERE card_code='NDT-EC-102'").fetchone()['id']
    original=client.get(f'/cards/{cid}')
    assert 'Kart atölyeye ulaştı' in original.text
    client.post(f'/cards/{cid}/assign',data={'csrf':admin,'assignee_id':str(other_id)},follow_redirects=True)
    with site.conn() as db:
        card=db.execute('SELECT latest_note,latest_note_by FROM cards WHERE id=?',(cid,)).fetchone()
    assert 'Kart atölyeye ulaştı' in card['latest_note']
    assert card['latest_note_by']==1  # Original demo admin, not assignee
    assert 'Sorumlu atandı' in client.get(f'/cards/{cid}').text

# V4 calendar and account management regression tests.
def test_shared_calendar_displays_planned_cards_for_both_roles(client):
    token = enter(client)
    with site.conn() as db:
        card = db.execute("SELECT planned_date,workshop,card_code FROM cards WHERE card_code='NDT-EC-102'").fetchone()
    month = card['planned_date'][:7]
    query = f'/dashboard?month={month}&day={card["planned_date"]}&location={card["workshop"]}'
    page = client.get(query)
    assert page.status_code == 200
    assert 'Hangi gün hangi kart gelecek?' in page.text
    assert card['card_code'] in page.text
    assert f'{card["planned_date"]}: 1 planlı kart' in page.text
    client.post('/logout', data={'csrf': token})
    enter(client, 'teknisyen', 'DemoTek123!')
    page = client.get(query)
    assert page.status_code == 200
    assert 'Hangi gün hangi kart gelecek?' in page.text
    assert card['card_code'] in page.text
    assert 'Bu güne kart ekle' not in page.text  # technician cannot create planned cards


def test_calendar_filters_location_without_exposing_other_location_cards(client):
    enter(client)
    with site.conn() as db:
        c = db.execute("SELECT planned_date FROM cards WHERE card_code='NDT-EC-102'").fetchone()
    # Unfiltered day contains ISL2; ISL1-only must not contain it in selected-day cards.
    filtered = site.build_calendar([
        {'planned_date': c['planned_date'], 'planned_time': '09:00', 'registration': 'DEMO-001',
         'card_code':'NDT-UT-TEST'}], month_value=c['planned_date'][:7], day_value=c['planned_date'],
         location='ISL1', path='/dashboard')
    assert filtered['day_cards'][0]['card_code'] == 'NDT-UT-TEST'
    page = client.get(f'/dashboard?month={c["planned_date"][:7]}&day={c["planned_date"]}&location=SAW')
    assert '0 kart' in page.text
    assert 'NDT-EC-102' not in page.text  # SAW filter also hides other locations from the table
    # Confirm page calendar has zero planned arrivals in SAW on the chosen date.
    assert f'{c["planned_date"]}: 0 planlı kart' in page.text


def test_admin_creates_technician_credentials_used_for_login(client):
    admin = enter(client)
    page = client.get('/users')
    assert 'Yeni teknisyen oluştur' in page.text
    username = 'yeni.teknisyen'
    password = 'GucluSifre123!'
    created = client.post('/users',data={'csrf':admin,'username':username,'full_name':'Yeni Teknisyen',
        'password':password,'role':'technician'},follow_redirects=True)
    assert 'Kullanıcı oluşturuldu' in created.text
    with site.conn() as db:
        row = db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        assert row['password_hash'] != password
        assert site.verify_password(password, row['password_hash'])
    client.post('/logout', data={'csrf':admin})
    technician = enter(client,username,password)
    page = client.get('/dashboard')
    assert 'Hangi gün hangi kart gelecek?' in page.text
    assert 'Yeni Teknisyen' in page.text
    assert client.get('/users').status_code == 403
    assert client.get('/cards/new').status_code == 403
    assert technician


def test_new_card_prefill_and_location_enforcement(client):
    token = enter(client)
    form = client.get('/cards/new?date=2026-11-14&location=IST')
    assert 'value="2026-11-14"' in form.text
    assert 'value="IST" selected' in form.text
    res = client.post('/cards/new',data={'csrf':token,'aircraft_id':1,'card_code':'BAD-LOC',
        'title':'Yanlış lokasyon','planned_date':'2026-11-14','workshop':'ISL / NDT'},follow_redirects=True)
    assert 'Bakım lokasyonu ISL1, ISL2, IST veya SAW olmalıdır' in res.text
    with site.conn() as db:
        assert db.execute("SELECT 1 FROM cards WHERE card_code='BAD-LOC'").fetchone() is None
    ok = client.post('/cards/new',data={'csrf':token,'aircraft_id':1,'card_code':'IST-2026-01',
        'title':'Takvime eklenecek bakım','planned_date':'2026-11-14','planned_time':'08:30',
        'workshop':'IST'},follow_redirects=False)
    assert ok.headers['location'].startswith('/cards/')
    page = client.get('/dashboard?month=2026-11&day=2026-11-14&location=IST')
    assert 'Takvime eklenecek bakım' in page.text


def test_invalid_calendar_inputs_fall_back_safely(client):
    enter(client)
    for url in ('/dashboard?month=2026-13&day=xxx&location=foo',
                '/dashboard?month=9999-01&day=9999-01-01',
                '/dashboard?month=2026-11&day=2025-10-05'):
        response = client.get(url)
        assert response.status_code == 200
        assert 'Hangi gün hangi kart gelecek?' in response.text
