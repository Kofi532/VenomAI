from datetime import timedelta
from decimal import Decimal
from hmac import compare_digest
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views import View
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
	EducationalMaterial,
	EnvenomationType,
	FirstAidStep,
	HealthFacility,
	PatientAssessment,
	PatientCase,
	Referral,
	Region,
	Snake,
	SnakeSighting,
	Symptom,
)
from .services import SnakebiteRiskEngine, _haversine_distance_km, get_nearby_antivenom_facilities
from .serializers import (
	AssessmentCreateSerializer,
	AssessmentResultSerializer,
	EducationalMaterialSerializer,
	BootstrapPayloadSerializer,
	FirstAidStepSerializer,
	HealthFacilityStockSerializer,
	SnakeDetailSerializer,
	SnakeListSerializer,
)


SNAKEBITE_ACCESS_SESSION_KEY = 'snakebite_access_granted'
SNAKEBITE_NATIONALITY_SESSION_KEY = 'snakebite_nationality'
SNAKEBITE_MEMBER_TYPE_SESSION_KEY = 'snakebite_member_type'
SNAKEBITE_PASSWORD_VERIFIED_SESSION_KEY = 'snakebite_password_verified'
SNAKEBITE_ASSESSMENT_SESSION_KEY = 'snakebite_assessment_data'

SNAKEBITE_NATIONALITY_OPTIONS = (
	('ghana', 'Ghana'),
	('malawi', 'Malawi'),
	('kenya', 'Kenya'),
	('nigeria', 'Nigeria'),
	('zambia', 'Zambia'),
)

SNAKEBITE_MEMBER_TYPE_OPTIONS = (
	('healthcare', 'Healthcare Member'),
	('community', 'Community Member'),
)

SNAKEBITE_COUNTRY_COORDINATES = {
	'ghana': {'latitude': 5.6037, 'longitude': -0.1870},
	'kenya': {'latitude': -1.2864, 'longitude': 36.8172},
	'malawi': {'latitude': -13.2543, 'longitude': 34.3015},
	'nigeria': {'latitude': 9.0820, 'longitude': 8.6753},
	'zambia': {'latitude': -15.3875, 'longitude': 28.3228},
}

SNAKEBITE_EMERGENCY_NUMBERS = {
	'ghana': '112',
	'kenya': '999',
	'malawi': '112',
	'nigeria': '112',
	'zambia': '991',
}

SNAKEBITE_COUNTRY_BOUNDS = {
	'ghana': {'min_latitude': 4.5, 'max_latitude': 11.5, 'min_longitude': -3.5, 'max_longitude': 1.2},
	'kenya': {'min_latitude': -4.7, 'max_latitude': 4.9, 'min_longitude': 33.9, 'max_longitude': 41.9},
	'malawi': {'min_latitude': -17.1, 'max_latitude': -9.2, 'min_longitude': 32.6, 'max_longitude': 35.9},
	'nigeria': {'min_latitude': 4.0, 'max_latitude': 14.7, 'min_longitude': 2.7, 'max_longitude': 14.7},
	'zambia': {'min_latitude': -18.1, 'max_latitude': -8.2, 'min_longitude': 21.9, 'max_longitude': 33.7},
}


def get_country_coordinates(country_code='ghana'):
	return SNAKEBITE_COUNTRY_COORDINATES.get((country_code or 'ghana').lower(), SNAKEBITE_COUNTRY_COORDINATES['ghana'])


def get_country_bounds(country_code='ghana'):
	return SNAKEBITE_COUNTRY_BOUNDS.get((country_code or 'ghana').lower(), SNAKEBITE_COUNTRY_BOUNDS['ghana'])


def get_country_label_for_coordinates(latitude, longitude):
	if latitude is None or longitude is None:
		return 'Unknown location'
	for country_code, bounds in SNAKEBITE_COUNTRY_BOUNDS.items():
		if (
			latitude >= bounds['min_latitude'] and latitude <= bounds['max_latitude'] and
			longitude >= bounds['min_longitude'] and longitude <= bounds['max_longitude']
		):
			return dict(SNAKEBITE_NATIONALITY_OPTIONS).get(country_code, country_code.title())
	return 'Global report'


def _resolve_member_type(request):
	member_type = (request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY) or '').strip().lower()
	if member_type:
		return member_type
	if getattr(request.user, 'is_authenticated', False):
		profile = getattr(request.user, 'userprofile', None)
		if profile is not None:
			profile_role = getattr(profile, 'role', None)
			if profile_role:
				return str(profile_role).strip().lower()
			profile_member_type = getattr(profile, 'member_type', None)
			if profile_member_type:
				return str(profile_member_type).strip().lower()
	return 'community'


def _persist_member_type(request, member_type):
	member_type = (member_type or '').strip().lower()
	if member_type not in {code for code, _ in SNAKEBITE_MEMBER_TYPE_OPTIONS}:
		return
	request.session[SNAKEBITE_MEMBER_TYPE_SESSION_KEY] = member_type
	if getattr(request.user, 'is_authenticated', False):
		profile = getattr(request.user, 'userprofile', None)
		if profile is not None:
			if hasattr(profile, 'member_type'):
				profile.member_type = member_type
				profile.save(update_fields=['member_type'])
			elif hasattr(profile, 'role'):
				profile.role = member_type
				profile.save(update_fields=['role'])


def snakebite_password_required(view_func):
	def wrapped_view(request, *args, **kwargs):
		if request.session.get(SNAKEBITE_ACCESS_SESSION_KEY):
			return view_func(request, *args, **kwargs)

		query = urlencode({'next': request.get_full_path()})
		return redirect(f"{reverse('snakebite:access')}?{query}")

	return wrapped_view


def _normalize_risk_level(risk_level):
	text = str(risk_level or 'LOW RISK').strip().upper().replace('_', ' ')
	if 'HIGH' in text:
		return 'high', 'HIGH RISK'
	if 'MEDIUM' in text:
		return 'medium', 'MEDIUM RISK'
	return 'low', 'LOW RISK'


def _assessment_risk_payload(assessment_result):
	severity_score = int(assessment_result.get('severity_score') or 0)
	patient_risk = PatientAssessment.calculate_risk_level(severity_score)
	canonical_key, canonical_label = _normalize_risk_level(patient_risk)
	assessment_result['risk_level'] = canonical_label
	assessment_result['risk_key'] = canonical_key
	return assessment_result


def _get_or_create_region_for_country(country_code='ghana'):
	country_code = (country_code or 'ghana').strip().lower()
	country_label = dict(SNAKEBITE_NATIONALITY_OPTIONS).get(country_code, 'Ghana')
	region = Region.objects.filter(code__iexact=country_code).first()
	if region is not None:
		return region
	region = Region.objects.filter(name__iexact=country_label).first()
	if region is not None:
		return region
	return Region.objects.create(name=country_label, code=country_code)


def _persist_assessment_from_session(request):
	assessment_session = request.session.get(SNAKEBITE_ASSESSMENT_SESSION_KEY, {}) or {}
	if not isinstance(assessment_session, dict):
		return None
	if assessment_session.get('assessment_id'):
		try:
			return PatientAssessment.objects.get(pk=assessment_session['assessment_id'])
		except PatientAssessment.DoesNotExist:
			pass
	result = request.session.get('snakebite_assessment_result') or {}
	country_code = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or 'ghana').strip().lower()
	region = _get_or_create_region_for_country(country_code)
	selected_symptoms = assessment_session.get('symptoms', []) or []
	symptom_objects = []
	for symptom_name in selected_symptoms:
		symptom_name = str(symptom_name).strip()
		if not symptom_name:
			continue
		slug = slugify(symptom_name)
		symptom = Symptom.objects.filter(slug=slug).first()
		if symptom is None:
			symptom = Symptom.objects.create(
				name=symptom_name.title(),
				slug=slug,
				body_system='General',
			)
		symptom_objects.append(symptom)
	severity_score = int(result.get('severity_score') or 0)
	predicted = result.get('predicted_envenomation') or 'Uncertain'
	envenomation = None
	if predicted and predicted.lower() != 'uncertain':
		envenomation = EnvenomationType.objects.filter(type_name__iexact=predicted).first()
	assessment = PatientAssessment.objects.create(
		region=region,
		patient_age_group='adult',
		predicted_envenomation=envenomation,
		severity_score=severity_score,
		risk_level=PatientAssessment.calculate_risk_level(severity_score),
		recommended_action='\n'.join(result.get('recommended_actions') or []),
	)
	if symptom_objects:
		assessment.symptoms_present.set(symptom_objects)
	assessment_session['assessment_id'] = assessment.pk
	request.session[SNAKEBITE_ASSESSMENT_SESSION_KEY] = assessment_session
	return assessment


def _first_aid_checklist_for_risk(risk_level, snake_type='other'):
	snake_key = str(snake_type or 'other').strip().lower()
	if FirstAidStep.objects.exists():
		steps = list(FirstAidStep.objects.order_by('step_number')[:4])
		if steps:
			return {
				'do': [step.do_statement for step in steps],
				'dont': [step.dont_statement for step in steps],
			}

	base_map = {
		'high': {
			'viper': [
				'Keep the patient calm and still.',
				'Immobilize the bitten limb with a splint.',
				'Call emergency transport immediately.',
			],
			'cobra': [
				'Keep the patient still and elevate the airway if needed.',
				'Do not delay transport to a facility with antivenom.',
				'Monitor breathing and watch for swelling.',
			],
			'mamba': [
				'Keep the person still and reassure them.',
				'Immobilize the limb and arrange urgent transfer.',
				'Do not wait for symptoms to worsen before seeking care.',
			],
			'other': [
				'Keep the patient calm and still.',
				'Immobilize the affected limb.',
				'Go to the nearest emergency facility now.',
			],
		},
		'medium': {
			'viper': [
				'Immobilize the limb and keep it below heart level.',
				'Monitor for rapid swelling or bleeding.',
				'Seek urgent clinical review.',
			],
			'cobra': [
				'Watch for breathing difficulty or blurred vision.',
				'Remove jewellery and keep the patient calm.',
				'Get professional assessment without delay.',
			],
			'mamba': [
				'Keep the patient still and avoid exertion.',
				'Seek emergency assessment while symptoms are monitored.',
				'Do not delay referral for observation.',
			],
			'other': [
				'Immobilize the area and monitor symptoms closely.',
				'Seek professional care promptly.',
				'Do not delay if symptoms worsen.',
			],
		},
		'low': {
			'viper': [
				'Wash the bite with clean water and keep the area still.',
				'Monitor for swelling or pain over the next hours.',
				'Attend clinic if symptoms appear or worsen.',
			],
			'cobra': [
				'Watch for any breathing changes or weakness.',
				'Keep the patient calm and observe closely.',
				'Seek care if symptoms start changing.',
			],
			'mamba': [
				'Rest and avoid movement while observing closely.',
				'Check for any new weakness or swelling.',
				'Contact a clinic if symptoms progress.',
			],
			'other': [
				'Keep the patient calm and observe the bite site.',
				'Seek a quick clinical review for reassurance.',
				'Return immediately if symptoms worsen.',
			],
		},
	}
	return {
		'do': base_map.get(risk_level, base_map['high']).get(snake_key, base_map['high']['other']),
		'dont': [
			'Do not cut or suck the wound.',
			'Do not apply a tight tourniquet.',
			'Do not delay referral to a clinic or hospital.',
		],
	}


def access_view(request):
	next_url = request.GET.get('next') or request.POST.get('next') or reverse('snakebite:home')
	if not next_url.startswith('/snakebite/'):
		next_url = reverse('snakebite:home')

	reset_access = (request.GET.get('reset_access') or request.POST.get('reset_access')) == '1'
	if reset_access:
		request.session.pop(SNAKEBITE_ACCESS_SESSION_KEY, None)
		request.session.pop(SNAKEBITE_PASSWORD_VERIFIED_SESSION_KEY, None)
		request.session.pop(SNAKEBITE_NATIONALITY_SESSION_KEY, None)
		request.session.pop(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, None)

	change_profile_requested = (request.GET.get('change_profile') or request.POST.get('change_profile')) == '1'
	password_verified = bool(request.session.get(SNAKEBITE_PASSWORD_VERIFIED_SESSION_KEY))
	access_granted = bool(request.session.get(SNAKEBITE_ACCESS_SESSION_KEY))
	can_edit_profile = password_verified or (access_granted and change_profile_requested)
	show_profile_form = request.GET.get('step') == 'profile' and can_edit_profile

	if request.method == 'GET' and access_granted and not change_profile_requested and request.GET.get('step') != 'profile' and not reset_access:
		return redirect(next_url)

	if request.method == 'GET' and password_verified and request.GET.get('step') != 'profile':
		return redirect(f"{reverse('snakebite:access')}?{urlencode({'next': next_url, 'step': 'profile'})}")

	nationality_values = {value for value, _ in SNAKEBITE_NATIONALITY_OPTIONS}
	member_type_values = {value for value, _ in SNAKEBITE_MEMBER_TYPE_OPTIONS}
	error_message = ''
	selected_nationality = request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY, '')
	selected_member_type = request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, '')
	if request.method == 'POST':
		action = request.POST.get('action', 'password')

		if action == 'password':
			password_input = request.POST.get('password', '')
			expected_password = 'Dr.EricNyarko'
			if not compare_digest(password_input, expected_password):
				error_message = 'Incorrect password. Please try again.'
			else:
				request.session[SNAKEBITE_PASSWORD_VERIFIED_SESSION_KEY] = True
				return redirect(f"{reverse('snakebite:access')}?{urlencode({'next': next_url, 'step': 'profile'})}")

		elif action == 'profile':
			if not can_edit_profile:
				error_message = 'Please confirm your password first.'
			else:
				selected_nationality = request.POST.get('nationality', '').strip().lower()
				selected_member_type = request.POST.get('member_type', '').strip().lower()
				if selected_nationality not in nationality_values:
					error_message = 'Please select your nationality to continue.'
				elif selected_member_type not in member_type_values:
					error_message = 'Please select whether you are a Healthcare or Community member.'
				else:
					request.session[SNAKEBITE_ACCESS_SESSION_KEY] = True
					request.session[SNAKEBITE_NATIONALITY_SESSION_KEY] = selected_nationality
					request.session[SNAKEBITE_MEMBER_TYPE_SESSION_KEY] = selected_member_type
					request.session.pop(SNAKEBITE_PASSWORD_VERIFIED_SESSION_KEY, None)
					if selected_member_type == 'community':
						return redirect(reverse('snakebite:community_home'))
					if selected_member_type == 'healthcare':
						return redirect(reverse('snakebite:chw_home'))
					return redirect(next_url)
		else:
			error_message = 'Invalid request. Please try again.'

	return render(
		request,
		'snakebite/access.html',
		{
			'next_url': next_url,
			'error_message': error_message,
			'nationality_options': SNAKEBITE_NATIONALITY_OPTIONS,
			'member_type_options': SNAKEBITE_MEMBER_TYPE_OPTIONS,
			'selected_nationality': selected_nationality,
			'selected_member_type': selected_member_type,
			'show_profile_form': show_profile_form,
			'can_edit_profile': can_edit_profile,
			'change_profile_requested': change_profile_requested,
		},
	)


@snakebite_password_required
def home_view(request):
	member_type = _resolve_member_type(request)
	if member_type == 'healthcare':
		return redirect('snakebite:chw_home')
	if member_type == 'community':
		return redirect('snakebite:community_home')

	sightings = SnakeSighting.objects.select_related('suspected_species').order_by('-created_at')[:20]
	species = Snake.objects.order_by('common_name')
	time_options = SnakeSighting.TimeSeenChoices.choices
	return render(
		request,
		'home_timeline.html',
		{
			'sightings': sightings,
			'species': species,
			'time_options': time_options,
			'report_url': reverse('snakebite:report_sighting'),
		},
	)


def _active_sighting_count():
	cutoff = timezone.now() - timedelta(days=7)
	count = 0
	for sighting in SnakeSighting.objects.filter(created_at__gte=cutoff).select_related('suspected_species'):
		if sighting.was_bitten or _derive_sighting_risk_level(sighting) == 'HIGH':
			count += 1
	return count


def _derive_sighting_risk_level(sighting):
	if sighting.was_bitten:
		return 'HIGH'
	if sighting.suspected_species and sighting.suspected_species.venom_type == 'hemotoxic':
		return 'HIGH'
	if sighting.suspected_species and sighting.suspected_species.venom_type:
		return 'MEDIUM'
	return 'LOW'


@snakebite_password_required
def get_sightings_api(request):
	filter_name = (request.GET.get('filter') or '').lower()
	queryset = SnakeSighting.objects.select_related('suspected_species').order_by('-created_at')

	selected_country = request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY, 'ghana').lower()
	valid_country_filters = {code for code, _ in SNAKEBITE_NATIONALITY_OPTIONS}
	if filter_name in {'nearby', 'global'}:
		if filter_name == 'global':
			queryset = queryset
		else:
			country_bounds = get_country_bounds(selected_country)
			queryset = queryset.filter(
				latitude__gte=country_bounds['min_latitude'],
				latitude__lte=country_bounds['max_latitude'],
				longitude__gte=country_bounds['min_longitude'],
				longitude__lte=country_bounds['max_longitude'],
			)
	elif filter_name in valid_country_filters:
		country_bounds = get_country_bounds(filter_name)
		queryset = queryset.filter(
			latitude__gte=country_bounds['min_latitude'],
			latitude__lte=country_bounds['max_latitude'],
			longitude__gte=country_bounds['min_longitude'],
			longitude__lte=country_bounds['max_longitude'],
		)
	else:
		country_bounds = get_country_bounds(selected_country)
		queryset = queryset.filter(
			latitude__gte=country_bounds['min_latitude'],
			latitude__lte=country_bounds['max_latitude'],
			longitude__gte=country_bounds['min_longitude'],
			longitude__lte=country_bounds['max_longitude'],
		)

	payload = []
	for sighting in list(queryset)[:30]:
		species = sighting.suspected_species
		risk_level = _derive_sighting_risk_level(sighting)
		latitude = float(sighting.latitude) if sighting.latitude is not None else None
		longitude = float(sighting.longitude) if sighting.longitude is not None else None
		payload.append({
			'id': sighting.id,
			'snake_name': species.common_name if species else 'Unidentified Snake',
			'scientific_name': species.scientific_name if species else '',
			'venom_type': species.venom_type if species else 'Unknown',
			'headline': sighting.headline or 'Unknown location',
			'location': get_country_label_for_coordinates(latitude, longitude),
			'timestamp': sighting.created_at.strftime('%Y-%m-%d %I:%M %p'),
			'created_at': sighting.created_at.isoformat(),
			'risk_level': risk_level,
			'description': sighting.description or 'No additional notes reported.',
			'latitude': latitude if latitude is not None else 0.0,
			'longitude': longitude if longitude is not None else 0.0,
			'photo_url': sighting.photo.url if sighting.photo and hasattr(sighting.photo, 'url') else '',
			'reported_by': 'community_report',
		})

	response_payload = {
		'count': len(payload),
		'results': payload,
		'active_count': _active_sighting_count(),
		'filter': filter_name,
	}
	return JsonResponse(response_payload, safe=False)


@snakebite_password_required
def sighting_api_detail(request, id):
	try:
		sighting = SnakeSighting.objects.select_related('suspected_species').get(id=id)
	except SnakeSighting.DoesNotExist:
		return JsonResponse({'error': 'Sighting not found'}, status=404)

	selected_country = request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY, 'ghana').lower()
	species = sighting.suspected_species
	latitude = float(sighting.latitude) if sighting.latitude is not None else None
	longitude = float(sighting.longitude) if sighting.longitude is not None else None
	data = {
		'id': sighting.id,
		'snake_name': species.common_name if species else 'Unidentified Snake',
		'headline': sighting.headline or 'Unknown location',
		'location': get_country_label_for_coordinates(latitude, longitude),
		'timestamp': sighting.created_at.strftime('%Y-%m-%d %I:%M %p'),
		'created_at': sighting.created_at.isoformat(),
		'risk_level': _derive_sighting_risk_level(sighting),
		'description': sighting.description or 'No additional details available.',
		'venom_type': species.venom_type if species else 'Unknown',
		'latitude': latitude if latitude is not None else 0.0,
		'longitude': longitude if longitude is not None else 0.0,
		'photo_url': sighting.photo.url if sighting.photo and hasattr(sighting.photo, 'url') else '',
	}
	return JsonResponse(data)


@snakebite_password_required
def sighting_detail_view(request, id):
	sighting = get_object_or_404(
		SnakeSighting.objects.select_related('suspected_species'),
		pk=id,
	)
	return render(
		request,
		'snakebite/sighting_detail.html',
		{
			'sighting': sighting,
			'risk_level': _derive_sighting_risk_level(sighting),
		},
	)


@snakebite_password_required
def chw_home_view(request):
	member_type = _resolve_member_type(request)
	if member_type != 'healthcare':
		return redirect('snakebite:home')
	return CHWDashboardView.as_view()(request)


@snakebite_password_required
def community_home_view(request):
	member_type = _resolve_member_type(request)
	if member_type == 'healthcare':
		return redirect('snakebite:chw_home')
	if member_type != 'community':
		request.session[SNAKEBITE_MEMBER_TYPE_SESSION_KEY] = 'community'

	selected_country = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or '').strip().lower()
	country_labels = dict(SNAKEBITE_NATIONALITY_OPTIONS)
	if request.method == 'POST' and 'nationality' in request.POST:
		country_code = (request.POST.get('nationality') or '').strip().lower()
		if country_code in {code for code, _ in SNAKEBITE_NATIONALITY_OPTIONS}:
			request.session[SNAKEBITE_NATIONALITY_SESSION_KEY] = country_code
			selected_country = country_code
			return redirect('snakebite:community_home')
	selected_country = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or selected_country or '').strip().lower()
	return render(
		request,
		'snakebite/community_home.html',
		{
			'nationality_label': selected_country,
			'member_type_label': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, ''),
			'active_count': _active_sighting_count(),
			'country_options': SNAKEBITE_NATIONALITY_OPTIONS,
			'selected_country': selected_country,
			'selected_country_label': country_labels.get(selected_country, 'Ghana'),
		},
	)


@snakebite_password_required
def community_bite_assessment_view(request):
	selected_country = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or 'ghana').strip().lower()
	country_label = dict(SNAKEBITE_NATIONALITY_OPTIONS).get(selected_country, 'Ghana')
	symptoms = list(Symptom.objects.order_by('body_system', 'name'))
	assessment_data = request.session.get(SNAKEBITE_ASSESSMENT_SESSION_KEY, {})
	if not isinstance(assessment_data, dict):
		assessment_data = {}

	current_step = request.POST.get('step') or request.GET.get('step') or '1'
	try:
		current_step = int(current_step)
	except (TypeError, ValueError):
		current_step = 1
	current_step = max(1, min(current_step, 4))

	if request.method == 'POST':
		if current_step == 1:
			snake_type = (request.POST.get('snake_type') or 'other').strip().lower()
			assessment_data['snake_type'] = snake_type
			request.session[SNAKEBITE_ASSESSMENT_SESSION_KEY] = assessment_data
			return redirect(f"{reverse('snakebite:community_bite_assessment')}?step=2")

		if current_step == 2:
			selected_symptoms = request.POST.getlist('symptoms')
			assessment_data['symptoms'] = selected_symptoms
			assessment_data['location'] = request.POST.get('location') or country_label
			request.session[SNAKEBITE_ASSESSMENT_SESSION_KEY] = assessment_data

			assessment_result = SnakebiteRiskEngine().assess_risk(selected_symptoms or ['swelling'])
			assessment_result['snake_type'] = assessment_data.get('snake_type', 'unknown')
			assessment_result['location'] = assessment_data.get('location', country_label)
			request.session['snakebite_assessment_result'] = _assessment_risk_payload(assessment_result)
			_ = _persist_assessment_from_session(request)
			return redirect(f"{reverse('snakebite:community_bite_assessment')}?step=3")

	if current_step == 3:
		assessment_result = request.session.get('snakebite_assessment_result') or {
			'risk_level': 'HIGH RISK',
			'predicted_envenomation': 'Uncertain',
			'likely_snakes': ['Viper', 'Mamba'],
			'severity_score': 52,
			'recommended_actions': ['Start First Aid / Splint Limb', 'Do NOT cut or suck wound', 'Stabilize Patient & Administer Antivenom', 'Urgent Referral to nearest facility'],
			'snake_type': assessment_data.get('snake_type', 'viper'),
			'location': assessment_data.get('location', country_label),
		}
		assessment_result = _assessment_risk_payload(assessment_result)
		request.session['snakebite_assessment_result'] = assessment_result
		_ = _persist_assessment_from_session(request)
		risk_key = assessment_result.get('risk_key', 'high')
		first_aid = _first_aid_checklist_for_risk(risk_key, assessment_result.get('snake_type', 'other'))
		return render(
			request,
			'snakebite/risk_result.html',
			{
				'nationality_label': selected_country,
				'member_type_label': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, ''),
				'country_label': country_label,
				'assessment_result': assessment_result,
				'location_label': assessment_result.get('location', country_label),
				'risk_color': risk_key,
				'risk_label': 'High Risk' if risk_key == 'high' else 'Medium Risk' if risk_key == 'medium' else 'Low Risk',
				'risk_banner_text': 'High Risk — Seek care immediately' if risk_key == 'high' else 'Medium Risk — Get prompt clinical review' if risk_key == 'medium' else 'Low Risk — Monitor and seek care if worsening',
				'first_aid_do': first_aid['do'],
				'first_aid_dont': first_aid['dont'],
				'current_step': 3,
			},
		)

	if current_step == 4:
		selected_country = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or 'ghana').strip().lower()
		country_label = dict(SNAKEBITE_NATIONALITY_OPTIONS).get(selected_country, 'Ghana')
		emergency_number = SNAKEBITE_EMERGENCY_NUMBERS.get(selected_country, '112')
		country_coordinates = get_country_coordinates(selected_country)
		facilities = get_nearby_antivenom_facilities(
			country_coordinates['latitude'],
			country_coordinates['longitude'],
			max_distance_km=300,
		)
		if not facilities:
			facilities = [{
				'facility_name': 'National Health Facility',
				'facility_type': 'Referral Center',
				'region': {'name': country_label},
				'antivenom_cost_ghs': 'Available on request',
				'contact_phone': emergency_number,
				'distance_km': 0,
			}]
		return render(
			request,
			'snakebite/nearest_help.html',
			{
				'nationality_label': selected_country,
				'member_type_label': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, ''),
				'country_label': country_label,
				'facilities': facilities,
				'primary_facility': facilities[0] if facilities else None,
				'emergency_number': emergency_number,
				'current_step': 4,
				'back_to_step_url': f"{reverse('snakebite:community_bite_assessment')}?step=3",
			},
		)

	return render(
		request,
		'snakebite/bite_assessment.html',
		{
			'nationality_label': selected_country,
			'member_type_label': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, ''),
			'country_label': country_label,
			'symptoms': symptoms,
			'selected_symptoms': set(assessment_data.get('symptoms', [])),
			'selected_snake': assessment_data.get('snake_type', 'viper'),
			'country_options': SNAKEBITE_NATIONALITY_OPTIONS,
			'selected_country': selected_country,
			'selected_country_label': country_label,
			'current_step': current_step,
		},
	)


@snakebite_password_required
def community_risk_result_view(request):
	assessment_result = request.session.get('snakebite_assessment_result') or {
		'risk_level': 'HIGH RISK',
		'predicted_envenomation': 'Uncertain',
		'likely_snakes': ['Viper', 'Mamba'],
		'severity_score': 52,
		'recommended_actions': ['Start First Aid / Splint Limb', 'Do NOT cut or suck wound', 'Stabilize Patient & Administer Antivenom', 'Urgent Referral to nearest facility'],
		'snake_type': 'viper',
		'location': 'Ghana',
	}
	assessment_result = _assessment_risk_payload(assessment_result)
	selected_country = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or 'ghana').strip().lower()
	country_label = dict(SNAKEBITE_NATIONALITY_OPTIONS).get(selected_country, 'Ghana')
	risk_key = assessment_result.get('risk_key', 'high')
	first_aid = _first_aid_checklist_for_risk(risk_key, assessment_result.get('snake_type', 'other'))
	return render(
		request,
		'snakebite/risk_result.html',
		{
			'nationality_label': selected_country,
			'member_type_label': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, ''),
			'country_label': country_label,
			'assessment_result': assessment_result,
			'location_label': assessment_result.get('location', country_label),
			'risk_color': risk_key,
			'risk_label': 'High Risk' if risk_key == 'high' else 'Medium Risk' if risk_key == 'medium' else 'Low Risk',
			'risk_banner_text': 'High Risk — Seek care immediately' if risk_key == 'high' else 'Medium Risk — Get prompt clinical review' if risk_key == 'medium' else 'Low Risk — Monitor and seek care if worsening',
			'first_aid_do': first_aid['do'],
			'first_aid_dont': first_aid['dont'],
			'current_step': 3,
		},
	)


@snakebite_password_required
def community_nearest_help_view(request):
	selected_country = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or 'ghana').strip().lower()
	country_label = dict(SNAKEBITE_NATIONALITY_OPTIONS).get(selected_country, 'Ghana')
	emergency_number = SNAKEBITE_EMERGENCY_NUMBERS.get(selected_country, '112')
	country_coordinates = get_country_coordinates(selected_country)
	facilities = get_nearby_antivenom_facilities(
		country_coordinates['latitude'],
		country_coordinates['longitude'],
		max_distance_km=300,
	)
	if not facilities:
		facilities = [{
			'facility_name': 'National Health Facility',
			'facility_type': 'Referral Center',
			'region': {'name': country_label},
			'antivenom_cost_ghs': 'Available on request',
			'contact_phone': emergency_number,
			'distance_km': 0,
			'antivenom_available': True,
		}]
	for facility in facilities:
		facility['status_label'] = 'Open 24/7' if facility.get('contact_phone') else 'Call ahead'
		facility['antivenom_label'] = 'Antivenom available' if facility.get('facility_name') else 'Antivenom available on request'
	return render(
		request,
		'snakebite/nearest_help.html',
		{
			'nationality_label': selected_country,
			'member_type_label': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, ''),
			'country_label': country_label,
			'facilities': facilities,
			'primary_facility': facilities[0] if facilities else None,
			'emergency_number': emergency_number,
			'current_step': 4,
		},
	)


@snakebite_password_required
def report_sighting_view(request):
	species = Snake.objects.order_by('common_name')
	time_options = SnakeSighting.TimeSeenChoices.choices
	form_errors = []
	prefill_sighting = None
	form_values = {
		'headline': '',
		'description': '',
		'contact_number': '',
		'suspected_species': '',
		'was_bitten': 'no',
		'time_seen': SnakeSighting.TimeSeenChoices.JUST_NOW,
	}

	similar_to = request.GET.get('similar_to')
	if similar_to:
		prefill_sighting = SnakeSighting.objects.select_related('suspected_species').filter(pk=similar_to).first()

	if request.method == 'POST':
		heading = (request.POST.get('headline') or '').strip()
		description = (request.POST.get('description') or '').strip()
		photo = request.FILES.get('photo')
		species_value = (request.POST.get('suspected_species') or '').strip()
		species_obj = None
		if species_value:
			if species_value.isdigit():
				species_obj = Snake.objects.filter(pk=species_value).first()
			if species_obj is None:
				species_obj = Snake.objects.filter(common_name__iexact=species_value).first()
		species_name = species_obj.common_name if species_obj else species_value
		was_bitten = request.POST.get('was_bitten') == 'yes'
		contact_number = (request.POST.get('contact_number') or '').strip()
		time_seen = request.POST.get('time_seen') or SnakeSighting.TimeSeenChoices.JUST_NOW
		member_type = _resolve_member_type(request)
		selected_country = request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY, 'ghana').lower()
		country_labels = dict(SNAKEBITE_NATIONALITY_OPTIONS)
		default_coordinates = get_country_coordinates(selected_country)
		default_latitude = default_coordinates['latitude']
		default_longitude = default_coordinates['longitude']
		country_label = country_labels.get(selected_country, 'Ghana')
		form_values.update({
			'headline': heading,
			'description': description,
			'contact_number': contact_number,
			'suspected_species': species_name,
			'was_bitten': 'yes' if was_bitten else 'no',
			'time_seen': time_seen,
		})

		if not heading:
			form_errors.append('Headline is required.')
		if not description:
			form_errors.append('Please add a short description.')
		if not photo:
			form_errors.append('Please upload a photo.')

		if not form_errors:
			sighting = SnakeSighting.objects.create(
				photo=photo,
				headline=heading,
				description=description,
				was_bitten=was_bitten,
				contact_number=contact_number,
				time_seen=time_seen,
				suspected_species=species_obj,
				suspected_species_name=species_name,
				member_type=member_type,
				latitude=default_latitude,
				longitude=default_longitude,
			)
			case = PatientCase.objects.create(
				patient_name=heading[:150] or 'Reported snake case',
				patient_age=18,
				gender=PatientCase.Gender.FEMALE if not was_bitten else PatientCase.Gender.OTHER,
				location=country_label,
				symptoms=description,
				suspected_snake_type=species_name or 'Unspecified',
				risk_level=PatientCase.RiskLevel.HIGH if was_bitten else PatientCase.RiskLevel.MEDIUM,
				status=PatientCase.Status.OPEN,
				clinical_notes=(
					f"Reported via snake sighting. "
					f"Contact: {contact_number or 'Not provided'}. "
					f"Was bitten: {'Yes' if was_bitten else 'No'}. "
					f"Time seen: {dict(SnakeSighting.TimeSeenChoices.choices).get(time_seen, time_seen)}."
				),
				photo=photo,
				member_type=member_type,
			)
			messages.success(request, f'Report submitted successfully. Case {case.case_id} is now open for review.')
			return redirect('snakebite:case_details', pk=case.pk)
		if form_errors:
			messages.error(request, 'Report could not be submitted. Please review the highlighted fields.')

	selected_country = request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY, 'ghana').lower()
	country_labels = dict(SNAKEBITE_NATIONALITY_OPTIONS)
	default_coordinates = get_country_coordinates(selected_country)
	return render(
		request,
		'snakebite/report_sighting.html',
		{
			'species': species,
			'time_options': time_options,
			'form_errors': form_errors,
			'prefill_sighting': prefill_sighting,
			'form_values': form_values,
			'nationality_label': selected_country,
			'member_type_label': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, ''),
			'country_options': SNAKEBITE_NATIONALITY_OPTIONS,
			'selected_country': selected_country,
			'selected_country_label': country_labels.get(selected_country, 'Ghana'),
			'default_country_latitude': default_coordinates['latitude'],
			'default_country_longitude': default_coordinates['longitude'],
		},
	)


def home(request):
	# Backward compatibility with any existing imports expecting home().
	return home_view(request)


def _get_dashboard_summary():
	cases = PatientCase.objects.order_by('-created_at')
	active_cases = cases.filter(status__in=[PatientCase.Status.OPEN, PatientCase.Status.IN_TRANSIT])
	metric_cards = [
		{
			'key': 'active_cases',
			'label': 'Active Cases',
			'count': active_cases.count(),
			'url_name': 'case_metric_list',
			'url_param': 'active_cases',
		},
		{
			'key': 'risk_alerts',
			'label': 'Risk Alerts',
			'count': cases.filter(risk_level=PatientCase.RiskLevel.HIGH).count(),
			'url_name': 'case_metric_list',
			'url_param': 'risk_alerts',
		},
		{
			'key': 'referrals',
			'label': 'Referrals',
			'count': Referral.objects.filter(status__in=[Referral.Status.PENDING, Referral.Status.SENT]).count(),
			'url_name': 'case_metric_list',
			'url_param': 'referrals',
		},
		{
			'key': 'resolved',
			'label': 'Resolved',
			'count': cases.filter(status=PatientCase.Status.RESOLVED).count(),
			'url_name': 'case_metric_list',
			'url_param': 'resolved',
		},
	]
	latest_case = active_cases.first()
	return {
		'cases': cases,
		'active_cases': active_cases,
		'latest_case': latest_case,
		'priority_cases': active_cases[:4],
		'metric_cards': metric_cards,
		'total_cases': cases.count(),
		'high_risk_cases': cases.filter(risk_level=PatientCase.RiskLevel.HIGH).count(),
		'referrals_made': Referral.objects.count(),
		'completed_outcomes': cases.filter(status=PatientCase.Status.RESOLVED).count(),
		'new_alerts': cases.filter(risk_level=PatientCase.RiskLevel.HIGH, status=PatientCase.Status.OPEN).count(),
		'pending_referrals': Referral.objects.filter(status__in=[Referral.Status.PENDING, Referral.Status.SENT]).count(),
		'resource_count': EducationalMaterial.objects.count(),
	}


@method_decorator(snakebite_password_required, name='dispatch')
class CHWHomeView(View):
	def get(self, request, *args, **kwargs):
		member_type = _resolve_member_type(request)
		if member_type != 'healthcare':
			return redirect('snakebite:home')

		dashboard = _get_dashboard_summary()
		role_label = 'CHW'
		# Use the existing patient-referral alert stream instead of creating a parallel alert system.
		recent_alerts = []
		for case in dashboard['cases'][:3]:
			recent_alerts.append({
				'time': case.created_at,
				'message': f"High risk case reported: {case.case_id}",
				'case_url': reverse('snakebite:case_details', kwargs={'pk': case.pk}),
			})
		for referral in Referral.objects.order_by('-sent_at')[:2]:
			recent_alerts.append({
				'time': referral.sent_at,
				'message': f"Transport requested for {referral.case.case_id}",
				'case_url': reverse('snakebite:case_details', kwargs={'pk': referral.case.pk}),
			})
		recent_alerts = sorted(recent_alerts, key=lambda item: item['time'], reverse=True)[:5]
		return render(
			request,
			'snakebite/chw_home.html',
			{
				'role_label': role_label,
				'active_cases': dashboard['active_cases'].count(),
				'new_alerts': dashboard['new_alerts'],
				'pending_referrals': dashboard['pending_referrals'],
				'resource_count': dashboard['resource_count'],
				'priority_cases': dashboard['priority_cases'],
				'latest_case': dashboard['latest_case'],
				'metric_cards': dashboard['metric_cards'],
				'total_cases': dashboard['total_cases'],
				'high_risk_cases': dashboard['high_risk_cases'],
				'referrals_made': dashboard['referrals_made'],
				'completed_outcomes': dashboard['completed_outcomes'],
				'recent_alerts': recent_alerts,
			},
		)


@method_decorator(snakebite_password_required, name='dispatch')
class CaseDetailsView(View):
	def get(self, request, pk, *args, **kwargs):
		active_cases = PatientCase.objects.filter(status__in=[PatientCase.Status.OPEN, PatientCase.Status.IN_TRANSIT]).order_by('-created_at')
		case = active_cases.filter(pk=pk).first()
		if case is None:
			latest_case = active_cases.first()
			if latest_case is None:
				return redirect('snakebite:chw_home')
			return redirect('snakebite:case_details', pk=latest_case.pk)
		symptoms = [item.strip() for item in case.symptoms.splitlines() if item.strip()] or [
			'Severe pain',
			'Swelling',
			'Bleeding',
		]
		assessment = PatientAssessment.objects.filter(
			region__name__iexact=case.location,
		).order_by('-timestamp').first()
		if assessment is None:
			assessment = PatientAssessment.objects.select_related('region').order_by('-timestamp').first()
		if assessment is not None:
			symptom_names = [symptom.name for symptom in assessment.symptoms_present.all()[:5]]
			if symptom_names:
				symptoms = symptom_names
			if not assessment.predicted_envenomation_id and case.suspected_snake_type:
				assessment.predicted_envenomation = None
			if case.risk_level:
				assessment.risk_level = case.risk_level
			if assessment.risk_level == PatientAssessment.RiskLevel.HIGH:
				case_risk_label = 'High Risk'
			elif assessment.risk_level == PatientAssessment.RiskLevel.MEDIUM:
				case_risk_label = 'Medium Risk'
			else:
				case_risk_label = 'Low Risk'
		else:
			case_risk_label = 'High Risk' if case.risk_level == PatientCase.RiskLevel.HIGH else 'Medium Risk' if case.risk_level == PatientCase.RiskLevel.MEDIUM else 'Low Risk'
		recent_assessments = PatientAssessment.objects.select_related('region').order_by('-timestamp')[:5]
		facility = HealthFacility.objects.filter(antivenom_available=True).order_by('name').first() or HealthFacility.objects.order_by('name').first()
		if facility is None:
			facility = HealthFacility.objects.create(
				name='National Referral Facility',
				facility_type=HealthFacility.FacilityType.DISTRICT_HOSPITAL,
				region=Region.objects.order_by('name').first() or Region.objects.create(name='Ghana', code='ghana'),
				contact_number='+233200000000',
				antivenom_available=True,
			)
		return render(
			request,
			'snakebite/case_details.html',
			{
				'case': case,
				'case_risk_label': case_risk_label,
				'symptoms': symptoms,
				'active_cases': active_cases,
				'recent_assessments': recent_assessments,
				'assessment': assessment,
				'facility': facility,
				'facility_phone': facility.contact_number or '+233200000000',
			},
		)


@method_decorator(snakebite_password_required, name='dispatch')
class SendReferralView(View):
	def _case_summary(self, case):
		risk_label = 'High risk' if case.risk_level == PatientCase.RiskLevel.HIGH else 'Medium risk' if case.risk_level == PatientCase.RiskLevel.MEDIUM else 'Low risk'
		status_note = 'Patient stabilised and on the way.' if case.status == PatientCase.Status.IN_TRANSIT else 'Patient stabilised and awaiting transfer.'
		return f"{risk_label} envenoming. {status_note}"

	def _nearest_facility_context(self, request):
		selected_country = (request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY) or 'ghana').strip().lower()
		country_coordinates = get_country_coordinates(selected_country)
		nearby_facilities = get_nearby_antivenom_facilities(
			country_coordinates['latitude'],
			country_coordinates['longitude'],
			max_distance_km=300,
		)
		options = HealthFacility.objects.select_related('region').filter(antivenom_available=True).order_by('name')
		if not options.exists():
			options = HealthFacility.objects.select_related('region').order_by('name')

		suggested = None
		if nearby_facilities:
			for nearby in nearby_facilities:
				facility_obj = HealthFacility.objects.select_related('region').filter(name=nearby['facility_name']).first()
				if facility_obj is not None:
					suggested = {
						'facility': facility_obj,
						'distance_km': nearby.get('distance_km', 0),
						'status_label': 'Open 24/7' if nearby.get('contact_phone') else 'Call ahead',
						'antivenom_available': bool(nearby.get('facility_name')),
					}
					break
		if suggested is None:
			suggested_facility = options.first()
			suggested = {
				'facility': suggested_facility,
				'distance_km': 0,
				'status_label': 'Open 24/7' if suggested_facility and suggested_facility.contact_number else 'Call ahead',
				'antivenom_available': bool(suggested_facility and suggested_facility.antivenom_available),
			} if suggested_facility else None
		return {
			'facility_options': options,
			'suggested_facility': suggested,
			'nearby_facilities': nearby_facilities,
		}

	def get(self, request, pk, *args, **kwargs):
		case = PatientCase.objects.filter(pk=pk).first()
		if case is None:
			latest_case = PatientCase.objects.order_by('-created_at').first()
			if latest_case is None:
				return redirect('snakebite:chw_home')
			return redirect('snakebite:send_referral', pk=latest_case.pk)
		context = self._nearest_facility_context(request)
		default_note = self._case_summary(case)
		return render(
			request,
			'snakebite/send_referral.html',
			{
				'case': case,
				'facility_options': context['facility_options'],
				'suggested_facility': context['suggested_facility'],
				'nearby_facilities': context['nearby_facilities'],
				'default_note': default_note,
			},
		)

	def post(self, request, pk, *args, **kwargs):
		case = PatientCase.objects.filter(pk=pk).first()
		if case is None:
			latest_case = PatientCase.objects.order_by('-created_at').first()
			if latest_case is None:
				return redirect('snakebite:chw_home')
			return redirect('snakebite:send_referral', pk=latest_case.pk)
		facility_id = request.POST.get('facility_id')
		facility = HealthFacility.objects.filter(pk=facility_id).first() if facility_id else None
		if facility is None:
			context = self._nearest_facility_context(request)
			if context['suggested_facility']:
				facility = context['suggested_facility']['facility']
			else:
				facility = HealthFacility.objects.filter(antivenom_available=True).order_by('name').first() or HealthFacility.objects.order_by('name').first()
		note = (request.POST.get('referral_note') or '').strip() or self._case_summary(case)
		share_details = request.POST.get('share_details') in {'yes', 'true', 'on', '1'}
		referral, created = Referral.objects.get_or_create(
			case=case,
			defaults={
				'destination_facility': facility,
				'notes': note,
				'shared_patient_details': share_details,
				'status': Referral.Status.SENT,
			},
		)
		if not created:
			referral.destination_facility = facility
			referral.notes = note
			referral.shared_patient_details = share_details
			referral.status = Referral.Status.SENT
			referral.save(update_fields=['destination_facility', 'notes', 'shared_patient_details', 'status'])
		case.status = PatientCase.Status.IN_TRANSIT
		case.save(update_fields=['status'])
		return redirect('snakebite:case_details', pk=case.pk)


@method_decorator(snakebite_password_required, name='dispatch')
class CHWDashboardView(View):
	def get(self, request, *args, **kwargs):
		filter_name = (request.GET.get('filter') or 'all').strip().lower()
		cases = PatientCase.objects.order_by('-created_at')
		if filter_name == 'high':
			cases = cases.filter(risk_level=PatientCase.RiskLevel.HIGH)
		elif filter_name == 'open':
			cases = cases.filter(status__in=[PatientCase.Status.OPEN, PatientCase.Status.IN_TRANSIT])
		elif filter_name == 'resolved':
			cases = cases.filter(status=PatientCase.Status.RESOLVED)
		elif filter_name == 'referrals':
			cases = cases.filter(referrals__isnull=False).distinct()

		case_cards = []
		for case in cases[:20]:
			case_cards.append({
				'case': case,
				'case_id': case.case_id,
				'patient_name': case.patient_name,
				'location': case.location,
				'patient_age': case.patient_age,
				'risk_level': case.risk_level,
				'status': case.status,
				'created_at': case.created_at,
				'symptoms': [item.strip() for item in (case.symptoms or '').splitlines() if item.strip()] or ['Persistent pain', 'Swelling'],
				'photo_url': case.photo.url if case.photo and hasattr(case.photo, 'url') else '',
				'suspected_snake_type': case.suspected_snake_type or 'Unspecified',
			})

		recent_alerts = []
		for case in PatientCase.objects.order_by('-created_at')[:5]:
			risk_text = 'High risk' if case.risk_level == PatientCase.RiskLevel.HIGH else 'Medium risk' if case.risk_level == PatientCase.RiskLevel.MEDIUM else 'Low risk'
			recent_alerts.append({
				'time': case.created_at,
				'message': f"{risk_text} case reported: {case.case_id}",
				'case_url': reverse('snakebite:case_details', kwargs={'pk': case.pk}),
			})
		for referral in Referral.objects.order_by('-sent_at')[:3]:
			recent_alerts.append({
				'time': referral.sent_at,
				'message': f"Transport requested for {referral.case.case_id}",
				'case_url': reverse('snakebite:case_details', kwargs={'pk': referral.case.pk}),
			})
		recent_alerts = sorted(recent_alerts, key=lambda item: item['time'], reverse=True)[:5]

		stats = {
			'total_cases': PatientCase.objects.count(),
			'high_risk_cases': PatientCase.objects.filter(risk_level=PatientCase.RiskLevel.HIGH).count(),
			'referrals_made': Referral.objects.count(),
			'completed_outcomes': PatientCase.objects.filter(status=PatientCase.Status.RESOLVED).count(),
			'active_cases': PatientCase.objects.filter(status__in=[PatientCase.Status.OPEN, PatientCase.Status.IN_TRANSIT]).count(),
			'new_alerts': PatientCase.objects.filter(risk_level=PatientCase.RiskLevel.HIGH, status=PatientCase.Status.OPEN).count(),
		}
		role_label = 'CHW'

		return render(
			request,
			'snakebite/chw_dashboard.html',
			{
				'cases': case_cards,
				'filter_name': filter_name,
				'recent_alerts': recent_alerts,
				'total_cases': stats['total_cases'],
				'high_risk_cases': stats['high_risk_cases'],
				'referrals_made': stats['referrals_made'],
				'completed_outcomes': stats['completed_outcomes'],
				'active_cases': stats['active_cases'],
				'new_alerts': stats['new_alerts'],
				'latest_case': PatientCase.objects.order_by('-created_at').first(),
				'role_label': role_label,
			},
		)


@snakebite_password_required
def case_metric_list_view(request, metric):
	metric_map = {
		'active_cases': {
			'label': 'Active Cases',
			'queryset': PatientCase.objects.filter(status__in=[PatientCase.Status.OPEN, PatientCase.Status.IN_TRANSIT]).order_by('-created_at'),
		},
		'risk_alerts': {
			'label': 'Risk Alerts',
			'queryset': PatientCase.objects.filter(risk_level=PatientCase.RiskLevel.HIGH).order_by('-created_at'),
		},
		'referrals': {
			'label': 'Referrals',
			'queryset': PatientCase.objects.filter(referrals__isnull=False).distinct().order_by('-created_at'),
		},
		'resolved': {
			'label': 'Resolved',
			'queryset': PatientCase.objects.filter(status=PatientCase.Status.RESOLVED).order_by('-created_at'),
		},
	}
	metric_config = metric_map.get(metric)
	if metric_config is None:
		return redirect('snakebite:chw_home')

	latest_case = PatientCase.objects.filter(status__in=[PatientCase.Status.OPEN, PatientCase.Status.IN_TRANSIT]).order_by('-created_at').first()
	return render(
		request,
		'snakebite/case_metric_list.html',
		{
			'metric': metric,
			'metric_label': metric_config['label'],
			'cases': metric_config['queryset'],
			'latest_case': latest_case,
		},
	)


@snakebite_password_required
def first_aid_view(request):
	first_aid_steps = FirstAidStep.objects.order_by('step_number')
	emergency_number = '112'
	return render(
		request,
		'snakebite/first_aid.html',
		{
			'first_aid_steps': first_aid_steps,
			'emergency_number': emergency_number,
		},
	)


@snakebite_password_required
def identify_symptoms_view(request):
	symptoms = Symptom.objects.order_by('body_system', 'name')
	symptoms_by_system = {}

	def icon_for_symptom(body_system, symptom_name):
		body_system_lower = body_system.lower()
		symptom_name_lower = symptom_name.lower()

		if 'resp' in body_system_lower or 'breath' in symptom_name_lower:
			return 'lungs'
		if 'neuro' in body_system_lower or 'ptosis' in symptom_name_lower:
			return 'brain'
		if 'hemo' in body_system_lower or 'bleed' in symptom_name_lower:
			return 'drop'
		if 'renal' in body_system_lower or 'urine' in symptom_name_lower:
			return 'kidney'
		if 'cardio' in body_system_lower:
			return 'heart'
		if 'skin' in body_system_lower or 'swell' in symptom_name_lower:
			return 'bandage'
		return 'stethoscope'

	for symptom in symptoms:
		symptoms_by_system.setdefault(symptom.body_system, []).append(
			{
				'symptom': symptom,
				'icon': icon_for_symptom(symptom.body_system, symptom.name),
			}
		)

	assessment_result = None
	selected_symptoms = []
	if request.method == 'POST':
		selected_symptoms = request.POST.getlist('symptoms')
		engine = SnakebiteRiskEngine()
		assessment_result = engine.assess_risk(selected_symptoms)

	return render(
		request,
		'snakebite/identify_symptoms.html',
		{
			'symptoms': symptoms,
			'symptoms_by_system': symptoms_by_system,
			'selected_symptoms': set(selected_symptoms),
			'assessment_result': assessment_result,
		},
	)


@snakebite_password_required
def snakes_in_area_view(request):
	regions = Region.objects.order_by('name')
	active_region_id = request.GET.get('region_id')

	if not active_region_id and request.user.is_authenticated:
		if getattr(request.user, 'region_id', None):
			active_region_id = str(request.user.region_id)
		elif getattr(request.user, 'region', None) and getattr(request.user.region, 'id', None):
			active_region_id = str(request.user.region.id)

	if not active_region_id:
		default_region = Region.objects.filter(snakes__isnull=False).order_by('name').first() or Region.objects.order_by('name').first()
		if default_region is not None:
			active_region_id = str(default_region.id)

	snakes = Snake.objects.prefetch_related('region_distribution').all().order_by('common_name')
	active_region = None
	if active_region_id:
		snakes = snakes.filter(region_distribution__id=active_region_id).distinct()
		active_region = Region.objects.filter(id=active_region_id).first()

	selected_snake = None
	selected_snake_id = request.GET.get('snake_id')
	if selected_snake_id:
		selected_snake = snakes.filter(id=selected_snake_id).first()

	return render(
		request,
		'snakebite/snakes_in_area.html',
		{
			'regions': regions,
			'active_region_id': active_region_id,
			'active_region': active_region,
			'snakes': snakes,
			'selected_snake': selected_snake,
		},
	)


@snakebite_password_required
def education_training_view(request):
	category_config = [
		{'key': 'guideline', 'label': 'Guidelines', 'icon': 'clipboard'},
		{'key': 'first_aid', 'label': 'First Aid', 'icon': 'medical-bag'},
		{'key': 'biology', 'label': 'Biology', 'icon': 'dna'},
		{'key': 'video', 'label': 'Videos', 'icon': 'play'},
		{'key': 'poster', 'label': 'Posters', 'icon': 'poster'},
	]

	materials = EducationalMaterial.objects.order_by('category', 'title')
	grouped_categories = []
	for config in category_config:
		category_key = config['key']
		if category_key in {'first_aid', 'biology'}:
			category_materials = materials.none()
		else:
			category_materials = materials.filter(category=category_key)

		material_items = []
		for item in category_materials:
			download_url = item.file_attachment.url if item.file_attachment else ''
			resource_url = download_url or item.video_url
			material_items.append(
				{
					'id': item.id,
					'title': item.title,
					'category': item.category,
					'download_url': download_url,
					'video_url': item.video_url,
					'resource_url': resource_url,
					'is_downloadable': bool(download_url),
					'file_size_bytes': item.file_attachment.size if item.file_attachment else None,
					'offline_available': bool(download_url),
				}
			)

		grouped_categories.append(
			{
				'key': category_key,
				'label': config['label'],
				'icon': config['icon'],
				'total': len(material_items),
				'materials': material_items,
			}
		)

	category_totals = {category['key']: category['total'] for category in grouped_categories}

	return render(
		request,
		'snakebite/education_training.html',
		{
			'grouped_categories': grouped_categories,
			'category_totals': category_totals,
		},
	)


@snakebite_password_required
def antivenom_map_view(request):
	facilities = HealthFacility.objects.select_related('region').filter(antivenom_available=True).order_by('region__name', 'name')
	facilities_payload = []
	for facility in facilities:
		latitude = float(facility.latitude) if facility.latitude is not None else None
		longitude = float(facility.longitude) if facility.longitude is not None else None
		facilities_payload.append(
			{
				'id': facility.id,
				'name': facility.name,
				'facility_type': facility.get_facility_type_display(),
				'region': facility.region.name,
				'latitude': latitude,
				'longitude': longitude,
				'antivenom_available': facility.antivenom_available,
				'antivenom_cost': float(facility.antivenom_cost) if facility.antivenom_cost is not None else None,
				'contact_number': facility.contact_number,
			}
		)

	return render(
		request,
		'snakebite/antivenom_map.html',
		{
			'facilities': facilities,
			'facilities_payload': facilities_payload,
		},
	)


@snakebite_password_required
def resources_view(request):
	return render(request, 'snakebite/resources.html')


@snakebite_password_required
def settings_view(request):
	if request.method == 'POST':
		if request.POST.get('reset_access') == '1':
			request.session.pop(SNAKEBITE_ACCESS_SESSION_KEY, None)
			request.session.pop(SNAKEBITE_PASSWORD_VERIFIED_SESSION_KEY, None)
			request.session.pop(SNAKEBITE_NATIONALITY_SESSION_KEY, None)
			request.session.pop(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, None)
			return redirect('snakebite:access')

		country_code = (request.POST.get('nationality') or '').strip().lower()
		if country_code in {code for code, _ in SNAKEBITE_NATIONALITY_OPTIONS}:
			request.session[SNAKEBITE_NATIONALITY_SESSION_KEY] = country_code

		member_type = (request.POST.get('member_type') or '').strip().lower()
		if member_type in {code for code, _ in SNAKEBITE_MEMBER_TYPE_OPTIONS}:
			_persist_member_type(request, member_type)

		return redirect('snakebite:settings')

	return render(
		request,
		'snakebite/settings.html',
		{
			'language': 'English',
			'alert_radius': '500m',
			'nearest_catchers': [],
			'regions': Region.objects.order_by('name'),
			'emergency_number': '112',
			'member_type': request.session.get(SNAKEBITE_MEMBER_TYPE_SESSION_KEY, 'community'),
			'nationality': request.session.get(SNAKEBITE_NATIONALITY_SESSION_KEY, 'ghana'),
			'nationality_options': SNAKEBITE_NATIONALITY_OPTIONS,
			'member_type_options': SNAKEBITE_MEMBER_TYPE_OPTIONS,
			'access_granted': bool(request.session.get(SNAKEBITE_ACCESS_SESSION_KEY)),
		},
	)


class SnakeViewSet(viewsets.ReadOnlyModelViewSet):
	queryset = Snake.objects.prefetch_related('region_distribution').all()

	def get_serializer_class(self):
		if self.action == 'retrieve':
			return SnakeDetailSerializer
		return SnakeListSerializer


class FirstAidStepViewSet(viewsets.ReadOnlyModelViewSet):
	queryset = FirstAidStep.objects.all().order_by('step_number')
	serializer_class = FirstAidStepSerializer


class EducationalMaterialViewSet(viewsets.ReadOnlyModelViewSet):
	queryset = EducationalMaterial.objects.all().order_by('category', 'title')
	serializer_class = EducationalMaterialSerializer


class HealthFacilityStockViewSet(viewsets.ReadOnlyModelViewSet):
	queryset = HealthFacility.objects.select_related('region').all()
	serializer_class = HealthFacilityStockSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		region = self.request.query_params.get('region')
		antivenom_available = self.request.query_params.get('antivenom_available')

		if region:
			queryset = queryset.filter(region_id=region)
		if antivenom_available is not None:
			truthy_values = {'1', 'true', 'yes', 'on'}
			queryset = queryset.filter(antivenom_available=antivenom_available.lower() in truthy_values)

		return queryset.order_by('name')

	def get_serializer_context(self):
		context = super().get_serializer_context()
		patient_latitude = self.request.query_params.get('patient_latitude') or None
		patient_longitude = self.request.query_params.get('patient_longitude') or None
		context['patient_location'] = {
			'latitude': patient_latitude,
			'longitude': patient_longitude,
		}
		return context


class AssessmentCreateView(APIView):
	def post(self, request, *args, **kwargs):
		serializer = AssessmentCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		engine = SnakebiteRiskEngine()
		symptom_slugs = [symptom.slug for symptom in serializer.validated_data['symptoms_list']]
		assessment_result = engine.assess_risk(symptom_slugs)

		with transaction.atomic():
			assessment = PatientAssessment.objects.create(
				region=serializer.validated_data['region'],
				patient_age_group=serializer.validated_data['patient_age_group'],
				recommended_action='\n'.join(assessment_result['recommended_actions']),
			)
			assessment.symptoms_present.set(serializer.validated_data['symptoms_list'])

			predicted_envenomation = self._resolve_prediction(assessment_result['predicted_envenomation'])
			if predicted_envenomation is not None:
				assessment.predicted_envenomation = predicted_envenomation
				assessment.save(update_fields=['predicted_envenomation'])

			PatientAssessment.objects.filter(pk=assessment.pk).update(
				severity_score=assessment_result['severity_score'],
				risk_level=self._normalize_risk_level(assessment_result['risk_level']),
				recommended_action='\n'.join(assessment_result['recommended_actions']),
			)
			assessment.refresh_from_db()

		nearest_facility = self._nearest_stocked_facility(assessment, serializer.validated_data)

		payload = {
			'assessment_id': assessment.pk,
			'risk_level': assessment_result['risk_level'],
			'predicted_envenomation': assessment_result['predicted_envenomation'],
			'recommended_actions': assessment_result['recommended_actions'],
			'likely_snakes': assessment_result['likely_snakes'],
			'nearest_facility': nearest_facility,
			'severity_score': assessment_result['severity_score'],
		}
		output_serializer = AssessmentResultSerializer(payload)
		return Response(output_serializer.data, status=status.HTTP_201_CREATED)

	def _normalize_risk_level(self, risk_level):
		mapping = {
			'HIGH RISK': PatientAssessment.RiskLevel.HIGH,
			'MEDIUM RISK': PatientAssessment.RiskLevel.MEDIUM,
			'LOW RISK': PatientAssessment.RiskLevel.LOW,
		}
		return mapping.get(risk_level, PatientAssessment.RiskLevel.LOW)

	def _resolve_prediction(self, predicted_envenomation):
		if predicted_envenomation in {'Neurotoxic', 'Hemotoxic'}:
			return EnvenomationType.objects.filter(type_name__iexact=predicted_envenomation).first()
		return None

	def _nearest_stocked_facility(self, assessment, validated_data):
		patient_latitude = validated_data.get('patient_latitude')
		patient_longitude = validated_data.get('patient_longitude')

		queryset = HealthFacility.objects.select_related('region').filter(antivenom_available=True)
		region_id = assessment.region_id
		if region_id:
			queryset = queryset.filter(region_id=region_id)

		facilities = list(queryset)
		if not facilities:
			return None

		if patient_latitude is None or patient_longitude is None:
			facility = facilities[0]
			return HealthFacilityStockSerializer(facility).data

		best_facility = min(
			facilities,
			key=lambda facility: self._distance_km(
				Decimal(str(patient_latitude)),
				Decimal(str(patient_longitude)),
				facility.latitude,
				facility.longitude,
			),
		)
		context = {
			'patient_location': {
				'latitude': patient_latitude,
				'longitude': patient_longitude,
			}
		}
		return HealthFacilityStockSerializer(best_facility, context=context).data

	def _distance_km(self, patient_latitude, patient_longitude, facility_latitude, facility_longitude):
		if facility_latitude is None or facility_longitude is None:
			return float('inf')

		from math import atan2, cos, radians, sin, sqrt

		earth_radius_km = 6371.0
		latitude_delta = radians(float(facility_latitude - patient_latitude))
		longitude_delta = radians(float(facility_longitude - patient_longitude))
		patient_latitude_rad = radians(float(patient_latitude))
		facility_latitude_rad = radians(float(facility_latitude))
		a = sin(latitude_delta / 2) ** 2 + cos(patient_latitude_rad) * cos(facility_latitude_rad) * sin(longitude_delta / 2) ** 2
		return 2 * earth_radius_km * atan2(sqrt(a), sqrt(1 - a))


class SyncBootstrapView(APIView):
	def get(self, request, *args, **kwargs):
		snakes = Snake.objects.prefetch_related('region_distribution').all()
		health_facilities = HealthFacility.objects.select_related('region').all()

		payload = {
			'snakes': SnakeDetailSerializer(snakes, many=True).data,
			'health_facilities': HealthFacilityStockSerializer(health_facilities, many=True).data,
			'emergency_guides': [
				{
					'title': 'First Aid',
					'steps': [
						'Keep the patient calm and still.',
						'Splint the limb and remove constricting items.',
						'Do NOT cut, suck, or apply ice to the bite.',
					],
				},
				{
					'title': 'Referral',
					'steps': [
						'Urgently refer to the nearest equipped facility.',
						'Administer antivenom only in a clinical setting.',
					],
				},
			],
			'educational_content': [
				{
					'title': 'Recognize high-risk symptoms',
					'summary': 'Drooping eyelids, breathing difficulty, bleeding gums, and dark urine require urgent escalation.',
				},
				{
					'title': 'Stay prepared',
					'summary': 'Carry emergency contacts and know the nearest stocked health facility before travel.',
				},
			],
		}
		return Response(BootstrapPayloadSerializer(payload).data)


class NearbyAntivenomFacilitiesView(APIView):
	def get(self, request, *args, **kwargs):
		latitude = request.query_params.get('latitude')
		longitude = request.query_params.get('longitude')
		max_distance_km = request.query_params.get('max_distance_km', 50)
		region_id = request.query_params.get('region_id')

		if latitude is None or longitude is None:
			return Response(
				{'detail': 'latitude and longitude are required.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		nearby_facilities = get_nearby_antivenom_facilities(
			latitude=latitude,
			longitude=longitude,
			max_distance_km=max_distance_km,
			region_id=region_id,
		)
		return Response(
			{
				'count': len(nearby_facilities),
				'results': nearby_facilities,
			}
		)
