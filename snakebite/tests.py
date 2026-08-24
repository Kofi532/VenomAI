from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import HealthFacility, PatientAssessment, PatientCase, Referral, Region, SnakeSighting, Symptom


class SnakebiteAccessAndCHWTests(TestCase):
    def test_patient_case_generates_case_id(self):
        case = PatientCase.objects.create(
            patient_name='Amina Boateng',
            patient_age=22,
            location='Takoradi',
            symptoms='Severe pain\nSwelling',
            assigned_to='CHW Team 2',
        )

        self.assertTrue(case.case_id.startswith('VG-'))
        self.assertTrue(len(case.case_id.split('-')[-1]) >= 5)

    def test_chw_home_requires_access(self):
        response = self.client.get(reverse('snakebite:chw_home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/venomguard/access/', response.url)

    def test_chw_home_renders_for_healthcare_member(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:chw_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Healthcare Worker')

    def test_chw_home_dashboard_layout_uses_live_case_and_alert_counts(self):
        case = PatientCase.objects.create(
            patient_name='Mawusi Adofo',
            patient_age=26,
            location='Tema',
            symptoms='Severe pain\nSwelling',
            risk_level=PatientCase.RiskLevel.HIGH,
            status=PatientCase.Status.OPEN,
        )
        Referral.objects.create(
            case=case,
            status=Referral.Status.PENDING,
            notes='Urgent transfer requested',
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:chw_home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Good morning')
        self.assertContains(response, 'Role: CHW')
        self.assertContains(response, 'New Snakebite Case')
        self.assertContains(response, 'My Cases')
        self.assertContains(response, 'Recent Alerts')
        self.assertContains(response, 'High risk case reported')
        self.assertContains(response, 'Transport requested')

        self.assertContains(response, reverse('snakebite:case_details', kwargs={'pk': case.pk}))

    def test_chw_dashboard_reads_live_case_records_and_filter_controls(self):
        PatientCase.objects.create(
            patient_name='Clara Addo',
            patient_age=24,
            location='Accra',
            symptoms='Severe pain\nSwelling',
            risk_level=PatientCase.RiskLevel.HIGH,
            status=PatientCase.Status.OPEN,
        )
        PatientCase.objects.create(
            patient_name='Kojo Nkrumah',
            patient_age=31,
            location='Kumasi',
            symptoms='Pain\nNausea',
            risk_level=PatientCase.RiskLevel.MEDIUM,
            status=PatientCase.Status.RESOLVED,
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:chw_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clara Addo')
        self.assertContains(response, 'Kojo Nkrumah')
        self.assertContains(response, 'data-filter')
        self.assertContains(response, 'All Cases')
        self.assertContains(response, 'High Risk')
        self.assertContains(response, 'Report')
        self.assertContains(response, reverse('snakebite:report_sighting'))

    def test_dashboard_metric_list_uses_shared_healthcare_nav_and_timeline_style(self):
        PatientCase.objects.create(
            patient_name='Esi Abebrese',
            patient_age=22,
            location='Cape Coast',
            symptoms='Severe pain\nSwelling',
            risk_level=PatientCase.RiskLevel.HIGH,
            status=PatientCase.Status.OPEN,
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:case_metric_list', kwargs={'metric': 'active_cases'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'snakebite-mobile-nav')
        self.assertContains(response, '#07130f')
        self.assertContains(response, 'Active Cases')

    def test_case_details_redirects_to_latest_available_case_when_missing(self):
        case = PatientCase.objects.create(
            patient_name='Kwame Boateng',
            patient_age=28,
            location='Accra',
            symptoms='Severe pain\nSwelling',
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:case_details', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('snakebite:case_details', kwargs={'pk': case.pk}))

    def test_case_details_renders_uploaded_photo(self):
        case = PatientCase.objects.create(
            patient_name='Akosua Boateng',
            patient_age=31,
            location='Kumasi',
            symptoms='Severe pain\nSwelling',
            photo=SimpleUploadedFile(
                'case_photo.jpg',
                b'fake-image-data',
                content_type='image/jpeg',
            ),
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:case_details', kwargs={'pk': case.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, case.photo.url)
        self.assertContains(response, 'Patient photo')
        self.assertContains(response, 'img')

    def test_case_details_uses_timeline_style_layout(self):
        case = PatientCase.objects.create(
            patient_name='Akosua Boateng',
            patient_age=31,
            location='Kumasi',
            symptoms='Severe pain\nSwelling',
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:case_details', kwargs={'pk': case.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'timeline-page')
        self.assertContains(response, 'Case Details')
        self.assertContains(response, 'bottom-nav')
        self.assertContains(response, 'Record overview')
        self.assertContains(response, 'Clinical record')
        self.assertContains(response, 'Referral history')

    def test_role_switch_in_settings_changes_home_view_on_next_load(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        self.client.post(
            reverse('snakebite:settings'),
            {'member_type': 'healthcare'},
        )
        self.assertEqual(self.client.session['snakebite_member_type'], 'healthcare')

        home_response = self.client.get(reverse('snakebite:home'))
        self.assertEqual(home_response.status_code, 302)
        self.assertEqual(home_response.url, reverse('snakebite:chw_home'))

        chw_response = self.client.get(reverse('snakebite:chw_home'))
        self.assertEqual(chw_response.status_code, 200)
        self.assertContains(chw_response, 'Healthcare Worker')

    def test_community_home_uses_valid_nav_routes(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        self.assertEqual(reverse('snakebite:community_home'), '/venomguard/community-home/')
        self.assertEqual(reverse('snakebite:report_sighting'), '/venomguard/report/')
        self.assertEqual(reverse('snakebite:report'), '/venomguard/report/')
        self.assertEqual(reverse('snakebite:antivenom_map'), '/venomguard/antivenom-stock-map/')
        self.assertEqual(reverse('snakebite:map'), '/venomguard/map/')
        self.assertEqual(reverse('snakebite:settings'), '/venomguard/settings/')
        self.assertEqual(reverse('snakebite:education_training'), '/venomguard/education-training/')

        response = self.client.get(reverse('snakebite:community_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Start Bite Assessment')
        self.assertContains(response, 'First Aid Guide')
        self.assertContains(response, 'Find Nearest Help')
        self.assertContains(response, reverse('snakebite:first_aid'))
        self.assertContains(response, reverse('snakebite:community_nearest_help'))
        self.assertContains(response, reverse('snakebite:education_training'))

        learn_response = self.client.get(reverse('snakebite:education_training'))
        self.assertEqual(learn_response.status_code, 200)
        self.assertContains(learn_response, 'Education and Training')
        self.assertContains(learn_response, 'First Aid for Snakebite')

        settings_response = self.client.get(reverse('snakebite:settings'))
        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, 'Settings')

    def test_community_home_hides_country_picker_after_selection(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        response = self.client.get(reverse('snakebite:community_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Timeline')
        self.assertNotContains(response, 'name="nationality"')

    def test_community_home_renders_dark_timeline_layout(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        response = self.client.get(reverse('snakebite:community_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Timeline')
        self.assertContains(response, 'data-filter="ghana"')
        self.assertContains(response, 'data-filter="global"')
        self.assertNotContains(response, 'data-filter="nearby"')
        self.assertContains(response, 'bottom-nav')
        self.assertContains(response, 'Report')
        self.assertContains(response, reverse('snakebite:report'))

    def test_community_home_uses_logged_in_country_filter(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'kenya'
        session['snakebite_member_type'] = 'community'
        session.save()

        response = self.client.get(reverse('snakebite:community_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-filter="kenya"')
        self.assertContains(response, 'Kenya')
        self.assertNotContains(response, 'data-filter="ghana"')

    def test_nearby_filter_aliases_to_ghana_results(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        ghana_sighting = SnakeSighting.objects.create(
            headline='Ghana sighting',
            description='Inside Ghana bounds',
            latitude=5.6037,
            longitude=-0.1870,
        )
        outside_ghana = SnakeSighting.objects.create(
            headline='Outside Ghana',
            description='Not in Ghana bounds',
            latitude=12.5000,
            longitude=0.0000,
        )

        response = self.client.get(
            reverse('snakebite:sightings_api'),
            {'filter': 'nearby'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item['id'] for item in payload['results']]
        self.assertIn(ghana_sighting.id, ids)
        self.assertNotIn(outside_ghana.id, ids)

    def test_community_home_country_selector_updates_session_country(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_member_type'] = 'community'
        session.save()

        initial_response = self.client.get(reverse('snakebite:community_home'))
        self.assertEqual(initial_response.status_code, 200)
        self.assertContains(initial_response, 'name="nationality"')

        update_response = self.client.post(
            reverse('snakebite:community_home'),
            {'nationality': 'kenya'},
        )
        self.assertEqual(update_response.status_code, 302)
        self.assertEqual(self.client.session['snakebite_nationality'], 'kenya')

        selected_response = self.client.get(reverse('snakebite:community_home'))
        self.assertEqual(selected_response.status_code, 200)
        self.assertNotContains(selected_response, 'name="nationality"')

    def test_sightings_api_uses_selected_country_as_location(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'nigeria'
        session['snakebite_member_type'] = 'community'
        session.save()

        sighting = SnakeSighting.objects.create(
            headline='Snake seen near Lagos',
            description='Large snake near a drain',
            latitude=9.0820,
            longitude=8.6753,
        )

        response = self.client.get(reverse('snakebite:sightings_api'), {'filter': 'nigeria'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Nigeria', response.json()['results'][0]['location'])
        self.assertEqual(response.json()['results'][0]['location'], 'Nigeria')
        self.assertEqual(response.json()['results'][0]['id'], sighting.id)

    def test_global_timeline_keeps_each_sighting_real_country_location(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        sighting = SnakeSighting.objects.create(
            headline='Snake seen near Lagos',
            description='Large green snake by a roadside',
            latitude=9.0820,
            longitude=8.6753,
        )

        response = self.client.get(reverse('snakebite:sightings_api'), {'filter': 'global'})
        self.assertEqual(response.status_code, 200)

        payload = response.json()['results']
        item = next(item for item in payload if item['id'] == sighting.id)
        self.assertEqual(item['location'], 'Nigeria')

    def test_settings_update_changes_country_used_for_reports(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        self.client.post(
            reverse('snakebite:settings'),
            {'nationality': 'nigeria'},
        )

        self.assertEqual(self.client.session['snakebite_nationality'], 'nigeria')

        photo = SimpleUploadedFile(
            'sighting.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near Lagos',
                'description': 'Large green snake by a roadside',
                'was_bitten': 'no',
                'contact_number': '+234700000000',
                'time_seen': 'just_now',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        sighting = SnakeSighting.objects.order_by('-pk').first()
        self.assertIsNotNone(sighting)
        self.assertEqual(float(sighting.latitude), 9.0820)
        self.assertEqual(float(sighting.longitude), 8.6753)

    def test_report_sighting_uses_selected_country_default_coordinates(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'kenya'
        session['snakebite_member_type'] = 'community'
        session.save()

        photo = SimpleUploadedFile(
            'sighting.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near Nairobi',
                'description': 'Large green snake by a roadside',
                'was_bitten': 'no',
                'contact_number': '+254700000000',
                'time_seen': 'just_now',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        sighting = SnakeSighting.objects.order_by('-pk').first()
        case = PatientCase.objects.order_by('-pk').first()
        self.assertIsNotNone(sighting)
        self.assertEqual(float(sighting.latitude), -1.2864)
        self.assertEqual(float(sighting.longitude), 36.8172)
        self.assertEqual(case.location, 'Kenya')

    def test_report_sighting_ignores_coordinates_from_client(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'kenya'
        session['snakebite_member_type'] = 'community'
        session.save()

        photo = SimpleUploadedFile(
            'sighting.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near Nairobi',
                'description': 'Large green snake by a roadside',
                'was_bitten': 'no',
                'time_seen': 'just_now',
                'latitude': '9.0820',
                'longitude': '8.6753',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        sighting = SnakeSighting.objects.order_by('-pk').first()
        self.assertEqual(float(sighting.latitude), -1.2864)
        self.assertEqual(float(sighting.longitude), 36.8172)

    def test_report_sighting_uses_zambia_country_default_coordinates(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'zambia'
        session['snakebite_member_type'] = 'community'
        session.save()

        photo = SimpleUploadedFile(
            'zambia_sighting.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near Lusaka',
                'description': 'Large green snake near a field',
                'was_bitten': 'no',
                'contact_number': '+260700000000',
                'time_seen': 'just_now',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        sighting = SnakeSighting.objects.order_by('-pk').first()
        case = PatientCase.objects.order_by('-pk').first()
        self.assertIsNotNone(sighting)
        self.assertEqual(float(sighting.latitude), -15.3875)
        self.assertEqual(float(sighting.longitude), 28.3228)
        self.assertEqual(case.location, 'Zambia')

    def test_report_sighting_uses_each_supported_country_default_coordinates(self):
        expected = {
            'ghana': {'latitude': 5.6037, 'longitude': -0.1870, 'label': 'Ghana'},
            'kenya': {'latitude': -1.2864, 'longitude': 36.8172, 'label': 'Kenya'},
            'malawi': {'latitude': -13.2543, 'longitude': 34.3015, 'label': 'Malawi'},
            'nigeria': {'latitude': 9.0820, 'longitude': 8.6753, 'label': 'Nigeria'},
            'zambia': {'latitude': -15.3875, 'longitude': 28.3228, 'label': 'Zambia'},
        }

        for country_code, values in expected.items():
            with self.subTest(country=country_code):
                session = self.client.session
                session['snakebite_access_granted'] = True
                session['snakebite_nationality'] = country_code
                session['snakebite_member_type'] = 'community'
                session.save()

                photo = SimpleUploadedFile(
                    f'{country_code}_sighting.jpg',
                    b'fake-image-data',
                    content_type='image/jpeg',
                )

                response = self.client.post(
                    reverse('snakebite:report_sighting'),
                    {
                        'headline': f'Snake seen in {country_code.title()}',
                        'description': 'Large snake near a roadside',
                        'was_bitten': 'no',
                        'contact_number': '+0000000000',
                        'time_seen': 'just_now',
                        'photo': photo,
                    },
                )

                self.assertEqual(response.status_code, 302)
                sighting = SnakeSighting.objects.order_by('-pk').first()
                case = PatientCase.objects.order_by('-pk').first()
                self.assertIsNotNone(sighting)
                self.assertEqual(float(sighting.latitude), values['latitude'])
                self.assertEqual(float(sighting.longitude), values['longitude'])
                self.assertEqual(case.location, values['label'])

    def test_report_sighting_saves_coordinates_for_timeline_filters(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        photo = SimpleUploadedFile(
            'sighting.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near school',
                'description': 'Large green snake by the road',
                'was_bitten': 'yes',
                'contact_number': '+233200000000',
                'time_seen': 'earlier_today',
                'latitude': '5.6037',
                'longitude': '-0.1870',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        sighting = SnakeSighting.objects.order_by('-pk').first()
        self.assertIsNotNone(sighting)
        self.assertEqual(float(sighting.latitude), 5.6037)
        self.assertEqual(float(sighting.longitude), -0.1870)

    def test_report_sighting_uses_default_ghana_coordinates_when_location_is_missing(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        photo = SimpleUploadedFile(
            'sighting.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near school',
                'description': 'Large green snake by the road',
                'was_bitten': 'yes',
                'contact_number': '+233200000000',
                'time_seen': 'earlier_today',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        sighting = SnakeSighting.objects.order_by('-pk').first()
        self.assertIsNotNone(sighting)
        self.assertEqual(float(sighting.latitude), 5.6037)
        self.assertEqual(float(sighting.longitude), -0.1870)

    def test_report_sighting_submits_selected_bite_and_time_values(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        photo = SimpleUploadedFile(
            'sighting.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near school',
                'description': 'Large green snake by the road',
                'was_bitten': 'yes',
                'contact_number': '+233200000000',
                'time_seen': 'earlier_today',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/venomguard/case-details/'))
        self.assertTrue(self.client.get(response.url).status_code == 200)

    def test_report_sighting_accepts_typed_species_name(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        photo = SimpleUploadedFile(
            'typed-species.jpg',
            b'fake-image-data',
            content_type='image/jpeg',
        )
        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near the market',
                'description': 'A snake was seen near the market entrance',
                'suspected_species': 'Green bush viper',
                'was_bitten': 'no',
                'time_seen': 'just_now',
                'photo': photo,
            },
        )

        self.assertEqual(response.status_code, 302)
        sighting = SnakeSighting.objects.order_by('-pk').first()
        case = PatientCase.objects.order_by('-pk').first()
        self.assertEqual(sighting.suspected_species_name, 'Green bush viper')
        self.assertIsNone(sighting.suspected_species)
        self.assertEqual(case.suspected_snake_type, 'Green bush viper')

    def test_report_sighting_keeps_existing_form_values_on_validation_error(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        response = self.client.post(
            reverse('snakebite:report_sighting'),
            {
                'headline': 'Snake seen near school',
                'description': '',
                'was_bitten': 'no',
                'contact_number': '+233200000000',
                'time_seen': 'just_now',
                'photo': SimpleUploadedFile(
                    'sighting.jpg',
                    b'fake-image-data',
                    content_type='image/jpeg',
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please add a short description.')
        self.assertContains(response, 'field-error')
        self.assertContains(response, 'Snake seen near school')
        self.assertContains(response, '+233200000000')
        self.assertContains(response, 'No')

    def test_bite_assessment_wizard_uses_existing_timeline_cards(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        response = self.client.get(reverse('snakebite:community_bite_assessment'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'timeline-page')
        self.assertContains(response, 'What type of snake bit the person?')
        self.assertContains(response, 'Assessment progress')
        self.assertContains(response, 'Risk result')

    def test_bite_assessment_posts_risk_result_and_nearest_help(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        region = Region.objects.create(name='Greater Accra', code='gh-01')
        HealthFacility.objects.create(
            name='Korle Bu Teaching Hospital',
            facility_type=HealthFacility.FacilityType.DISTRICT_HOSPITAL,
            region=region,
            latitude=5.6037,
            longitude=-0.1870,
            antivenom_available=True,
            antivenom_cost=150.00,
            contact_number='+233200000000',
        )

        step_one = self.client.post(
            reverse('snakebite:community_bite_assessment'),
            {
                'step': '1',
                'snake_type': 'viper',
            },
        )
        self.assertEqual(step_one.status_code, 302)
        self.assertEqual(step_one.url, reverse('snakebite:community_bite_assessment') + '?step=2')

        step_two = self.client.post(
            reverse('snakebite:community_bite_assessment') + '?step=2',
            {
                'step': '2',
                'symptoms': ['swelling', 'bleeding-gums'],
                'location': 'Ghana',
            },
        )
        self.assertEqual(step_two.status_code, 302)
        self.assertEqual(step_two.url, reverse('snakebite:community_bite_assessment') + '?step=3')

        step_three = self.client.get(reverse('snakebite:community_bite_assessment') + '?step=3')
        self.assertEqual(step_three.status_code, 200)
        self.assertContains(step_three, 'High Risk')
        self.assertContains(step_three, 'What to do now')
        self.assertContains(step_three, 'Find Nearest Help')
        self.assertContains(step_three, 'Call for Transport Help')

        step_four = self.client.get(reverse('snakebite:community_bite_assessment') + '?step=4')
        self.assertEqual(step_four.status_code, 200)
        self.assertContains(step_four, 'Nearest Help')
        self.assertContains(step_four, 'Emergency call')

        result_response = self.client.get(reverse('snakebite:community_risk_result'))
        self.assertEqual(result_response.status_code, 200)
        self.assertContains(result_response, 'High Risk')
        self.assertContains(result_response, 'Find nearest help')

        nearest_response = self.client.get(reverse('snakebite:community_nearest_help'))
        self.assertEqual(nearest_response.status_code, 200)
        self.assertContains(nearest_response, 'Korle Bu Teaching Hospital')

    def test_bite_assessment_risk_branches_low_and_high(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        self.client.post(
            reverse('snakebite:community_bite_assessment'),
            {'step': '1', 'snake_type': 'viper'},
        )
        low_risk = self.client.post(
            reverse('snakebite:community_bite_assessment') + '?step=2',
            {'step': '2', 'symptoms': ['itching'], 'location': 'Ghana'},
        )
        self.assertEqual(low_risk.status_code, 302)
        self.assertEqual(low_risk.url, reverse('snakebite:community_bite_assessment') + '?step=3')

        low_result = self.client.get(reverse('snakebite:community_bite_assessment') + '?step=3')
        self.assertContains(low_result, 'Low Risk')

        session = self.client.session
        session['snakebite_assessment_data'] = {'snake_type': 'viper', 'symptoms': ['swelling', 'bleeding-gums'], 'location': 'Ghana'}
        session['snakebite_assessment_result'] = {
            'risk_level': 'HIGH RISK',
            'severity_score': 52,
            'predicted_envenomation': 'Hemotoxic',
            'recommended_actions': ['Start First Aid / Splint Limb', 'Do NOT cut or suck wound', 'Stabilize Patient & Administer Antivenom', 'Urgent Referral to nearest facility'],
            'likely_snakes': ['Viper'],
            'snake_type': 'viper',
            'location': 'Ghana',
        }
        session.save()

        high_result = self.client.get(reverse('snakebite:community_bite_assessment') + '?step=3')
        self.assertContains(high_result, 'High Risk')

    def test_bite_assessment_creates_patient_assessment_record(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        self.client.post(
            reverse('snakebite:community_bite_assessment'),
            {'step': '1', 'snake_type': 'viper'},
        )
        self.client.post(
            reverse('snakebite:community_bite_assessment') + '?step=2',
            {'step': '2', 'symptoms': ['swelling', 'bleeding-gums'], 'location': 'Ghana'},
        )

        assessment_id = self.client.session.get('snakebite_assessment_data', {}).get('assessment_id')
        self.assertIsNotNone(assessment_id)
        assessment = PatientAssessment.objects.get(pk=assessment_id)
        self.assertTrue(assessment.symptoms_present.filter(slug='swelling').exists())
        self.assertEqual(assessment.region.code.lower(), 'ghana')

    def test_case_details_lists_recent_patient_assessments(self):
        region = Region.objects.create(name='Ghana', code='ghana')
        assessment = PatientAssessment.objects.create(
            region=region,
            patient_age_group='adult',
            risk_level=PatientAssessment.RiskLevel.HIGH,
            severity_score=52,
            recommended_action='Urgent referral',
        )
        assessment.symptoms_present.set([Symptom.objects.create(name='Swelling', slug='swelling', body_system='Extremity')])

        case = PatientCase.objects.create(
            patient_name='Akosua Boateng',
            patient_age=31,
            location='Accra',
            symptoms='Severe pain\nSwelling',
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:case_details', kwargs={'pk': case.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent assessments')
        self.assertContains(response, 'High')
        self.assertContains(response, 'Swelling')

    def test_case_details_shows_referral_and_call_actions_for_healthcare_users(self):
        region = Region.objects.create(name='Ghana', code='ghana')
        facility = HealthFacility.objects.create(
            name='Korle Bu Teaching Hospital',
            facility_type=HealthFacility.FacilityType.DISTRICT_HOSPITAL,
            region=region,
            contact_number='+233201234567',
            antivenom_available=True,
        )
        assessment = PatientAssessment.objects.create(
            region=region,
            patient_age_group='adult',
            risk_level=PatientAssessment.RiskLevel.HIGH,
            severity_score=58,
            recommended_action='Urgent referral',
        )
        assessment.symptoms_present.set([
            Symptom.objects.create(name='Swelling', slug='swelling', body_system='Extremity'),
            Symptom.objects.create(name='Bleeding', slug='bleeding', body_system='General'),
        ])

        case = PatientCase.objects.create(
            patient_name='Kwame Mensah',
            patient_age=19,
            location='Accra',
            symptoms='Severe pain\nSwelling\nBleeding',
            risk_level=PatientCase.RiskLevel.HIGH,
            status=PatientCase.Status.OPEN,
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:case_details', kwargs={'pk': case.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Send Referral')
        self.assertContains(response, 'Call Facility')
        self.assertContains(response, 'tel:+233201234567')
        self.assertContains(response, 'High Risk')
        self.assertContains(response, 'Swelling')

    def test_send_referral_screen_shows_nearest_facility_and_updates_referral_record(self):
        region = Region.objects.create(name='Ghana', code='ghana')
        facility = HealthFacility.objects.create(
            name='Korle Bu Teaching Hospital',
            facility_type=HealthFacility.FacilityType.DISTRICT_HOSPITAL,
            region=region,
            latitude=5.5500,
            longitude=-0.2000,
            contact_number='+233201234567',
            antivenom_available=True,
        )
        case = PatientCase.objects.create(
            patient_name='Ama Koomson',
            patient_age=34,
            location='Accra',
            symptoms='Severe pain\nSwelling',
            risk_level=PatientCase.RiskLevel.HIGH,
            status=PatientCase.Status.OPEN,
        )

        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'healthcare'
        session.save()

        response = self.client.get(reverse('snakebite:send_referral', kwargs={'pk': case.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Refer to Facility')
        self.assertContains(response, 'Korle Bu Teaching Hospital')
        self.assertContains(response, 'Antivenom available')
        self.assertContains(response, 'Open 24/7')
        self.assertContains(response, 'High risk envenoming')
        self.assertContains(response, 'Share patient details with receiving facility?')
        self.assertContains(response, 'Send Referral')
        self.assertContains(response, 'Cancel')

        post_response = self.client.post(
            reverse('snakebite:send_referral', kwargs={'pk': case.pk}),
            {
                'facility_id': str(facility.pk),
                'referral_note': 'High risk envenoming. Patient stabilised and on the way.',
                'share_details': 'on',
            },
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response.url, reverse('snakebite:case_details', kwargs={'pk': case.pk}))

        referral = Referral.objects.get(case=case)
        self.assertEqual(referral.destination_facility, facility)
        self.assertTrue(referral.shared_patient_details)
        self.assertEqual(referral.notes, 'High risk envenoming. Patient stabilised and on the way.')
        self.assertEqual(referral.status, Referral.Status.SENT)

        case.refresh_from_db()
        self.assertEqual(case.status, PatientCase.Status.IN_TRANSIT)

    def test_venomguard_pages_do_not_use_placeholder_links(self):
        session = self.client.session
        session['snakebite_access_granted'] = True
        session['snakebite_nationality'] = 'ghana'
        session['snakebite_member_type'] = 'community'
        session.save()

        education_response = self.client.get(reverse('snakebite:education_training'))
        self.assertEqual(education_response.status_code, 200)
        self.assertNotContains(education_response, 'href="#"')
        self.assertNotContains(education_response, 'href=""')

        help_response = self.client.get(reverse('snakebite:community_nearest_help'))
        self.assertEqual(help_response.status_code, 200)
        self.assertNotContains(help_response, 'href=""')

        snakes_response = self.client.get(reverse('snakebite:snakes_in_area'))
        self.assertEqual(snakes_response.status_code, 200)
        self.assertNotContains(snakes_response, 'href="#"')
