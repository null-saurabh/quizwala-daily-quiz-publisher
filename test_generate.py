import datetime as dt
import email.utils
import unittest
import tempfile
import json
import io
from unittest.mock import patch
from pathlib import Path

import generate


EDITION_DATE = dt.date(2026, 10, 22)
EVIDENCE = [{
    'id': '1',
    'title': 'Government announces a new national programme',
    'url': 'https://example.org/news',
    'published': '2026-10-22T00:00:00+00:00',
    'text': 'The programme will support public research and economic development across India.',
}]
QUOTE = 'The programme will support public research and economic development across India.'


def question(index):
    return {
        'source_id': '1',
        'evidence': QUOTE,
        'prompt': {'en': f'Which fact is supported by the report, question {index}?', 'hi': ''},
        'options': [
            {'id': option, 'text': {'en': f'Option {option} for {index}'}}
            for option in 'abcd'
        ],
        'correct_option_id': 'a',
        'explanation': {'en': 'The source states this directly.'},
    }


def topic(index, count=10):
    return {'title': f'Topic {index}', 'questions': [question(index * 100 + n) for n in range(count)]}


def publication(day):
    # Different dates have distinct facts; this exercises cross-day filtering.
    raw = {'sets': [topic(i + day.toordinal() * 10) for i in range(3)]}
    decks = generate.validate(raw, EVIDENCE, day)
    return generate.build_payload(decks, EVIDENCE, day, dt.datetime.now(dt.timezone.utc))


class DailyGenerationTests(unittest.TestCase):
    def test_evening_generation_targets_next_edition(self):
        for instant in ['2026-10-21T12:00:00+00:00', '2026-10-21T15:00:00+00:00', '2026-10-21T18:00:00+00:00']:
            self.assertEqual(generate.edition_for_run(dt.datetime.fromisoformat(instant)), EDITION_DATE)
        self.assertEqual(generate.edition_for_run(dt.datetime.fromisoformat('2026-12-31T16:00:00+00:00')), dt.date(2027, 1, 1))
        self.assertEqual(generate.edition_for_run(dt.datetime.fromisoformat('2028-02-28T16:00:00+00:00')), dt.date(2028, 2, 29))

    def test_scheduled_retries_resume_oldest_incomplete_before_new_tomorrow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            yesterday_target = EDITION_DATE - dt.timedelta(days=1)
            generate.reserve_attempt(yesterday_target, root)
            now = dt.datetime.fromisoformat('2026-10-22T05:05:00+00:00')  # 10:35 IST
            self.assertEqual(generate.target_for_run(now, root), yesterday_target)
            self.assertEqual(generate.reserve_attempt(generate.target_for_run(now, root), root), 2)
            generate.reserve_attempt(yesterday_target + dt.timedelta(days=1), root)
            self.assertEqual(generate.target_for_run(now, root), yesterday_target)
            self.assertEqual(generate.reserve_attempt(yesterday_target, root), 3)
            self.assertEqual(generate.reserve_attempt(yesterday_target, root), 4)
            self.assertEqual(generate.reserve_attempt(yesterday_target, root), 5)
            self.assertEqual(generate.target_for_run(now, root), yesterday_target + dt.timedelta(days=1))

    def test_request_claim_requires_reservation_and_can_only_be_used_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(SystemExit, 'reservation'):
                generate.claim_generation(EDITION_DATE, root)
            (root / 'state').mkdir()
            marker = root / 'state' / f'{EDITION_DATE}.json'
            marker.write_text(json.dumps({'date': str(EDITION_DATE), 'status': 'reserved'}))
            generate.claim_generation(EDITION_DATE, root)
            tomorrow = EDITION_DATE + dt.timedelta(days=1)
            (root / 'state' / f'{tomorrow}.json').write_text(json.dumps({'date': str(tomorrow), 'status': 'reserved'}))
            generate.claim_generation(tomorrow, root)
            # Simulates a failed or interrupted request before publication.
            with self.assertRaisesRegex(SystemExit, 'already attempted'):
                generate.claim_generation(EDITION_DATE, root)

    def test_published_or_wrong_day_reservations_cannot_trigger_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'state').mkdir()
            marker = root / 'state' / f'{EDITION_DATE}.json'
            for date, status in [(str(EDITION_DATE), 'published'), ('2026-10-21', 'reserved')]:
                marker.write_text(json.dumps({'date': date, 'status': status}))
                with self.assertRaisesRegex(SystemExit, 'not available'):
                    generate.claim_generation(EDITION_DATE, root)

    def test_archive_keeps_history_for_today_and_early_published_tomorrow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for offset in range(10):
                day = EDITION_DATE + dt.timedelta(days=offset)
                generate.publish(publication(day), root)
            history = json.loads((root / 'site/history.json').read_text())['editions']
            self.assertEqual(len(history), 8)
            self.assertEqual(history[0]['date'], str(EDITION_DATE + dt.timedelta(days=8)))
            self.assertEqual(history[-1]['date'], str(EDITION_DATE + dt.timedelta(days=1)))
            with self.assertRaisesRegex(ValueError, 'already published'):
                generate.publish(publication(day), root)

    def test_first_real_publication_does_not_archive_development_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'site').mkdir()
            (root / 'site/latest.json').write_text(json.dumps({'date': '2026-10-21', 'status': 'ready', 'sets': []}))
            generate.publish(publication(EDITION_DATE), root)
            self.assertEqual(json.loads((root / 'site/history.json').read_text())['editions'], [])
            self.assertFalse((root / 'site/editions/2026-10-21.json').exists())

    def test_partial_attempts_merge_without_changing_retained_ids_or_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = generate.validate({'sets': [topic(1, 8), topic(2, 10)]}, EVIDENCE, EDITION_DATE, partial=True)
            retained = generate.merge_candidate(first, EVIDENCE, EDITION_DATE, root)
            snapshot = json.loads(json.dumps(retained['sets']))
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                generate.candidate_payload(retained, EDITION_DATE)
            retry = generate.validate({'sets': [topic(1, 16), topic(2, 12), topic(3, 11)]}, EVIDENCE, EDITION_DATE, partial=True)
            retained = generate.merge_candidate(retry, EVIDENCE, EDITION_DATE, root)
            for deck, old in zip(retained['sets'], snapshot):
                self.assertEqual(deck['questions'][:len(old['questions'])], old['questions'])
            payload = generate.candidate_payload(retained, EDITION_DATE)
            self.assertEqual([len(d['questions']) for d in payload['sets']], [16, 12, 11])
            generate.publish(payload, root)
            before = (root / 'site/latest.json').read_bytes()
            self.assertIsNone(generate.reserve_attempt(EDITION_DATE, root))
            with self.assertRaisesRegex(ValueError, 'already published'):
                generate.publish(payload, root)
            self.assertEqual((root / 'site/latest.json').read_bytes(), before)

    def test_retries_bounded_per_edition_and_next_date_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for attempt in range(1, 6):
                self.assertEqual(generate.reserve_attempt(EDITION_DATE, root), attempt)
                self.assertEqual(generate.claim_generation(EDITION_DATE, root), attempt)
                with self.assertRaisesRegex(SystemExit, 'already attempted'):
                    generate.claim_generation(EDITION_DATE, root)
            self.assertIsNone(generate.reserve_attempt(EDITION_DATE, root))
            self.assertEqual(generate.reserve_attempt(EDITION_DATE + dt.timedelta(days=1), root), 1)

    def test_normalized_and_near_duplicates_across_attempts_and_previous_day(self):
        prompt = 'Which Indian institution launched the national research programme?'
        for variant in [prompt.upper(), 'Which Indian institution launched the national research programme!!!',
                        'Which institution in India launched the national research programme?']:
            self.assertTrue(generate.duplicate(variant, [prompt]))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = publication(EDITION_DATE - dt.timedelta(days=1))
            generate.publish(prior, root)
            previous = generate.previous_prompts(EDITION_DATE, root)
            raw = question(999)
            raw['prompt']['en'] = previous[0].upper()
            parsed = generate.validate({'sets': [{'title': 'Repeated', 'questions': [raw]}]}, EVIDENCE, EDITION_DATE, partial=True, previous=previous)
            self.assertEqual(parsed, [])
            raw['prompt']['en'] = prompt
            parsed = generate.validate({'sets': [{'title': 'Topic', 'questions': [raw]}]}, EVIDENCE, EDITION_DATE, partial=True)
            retained = generate.merge_candidate(parsed, EVIDENCE, EDITION_DATE, root)
            raw['prompt']['en'] = prompt.upper() + '!'
            parsed = generate.validate({'sets': [{'title': 'Different topic', 'questions': [raw]}]}, EVIDENCE, EDITION_DATE, partial=True)
            retained = generate.merge_candidate(parsed, EVIDENCE, EDITION_DATE, root)
            self.assertEqual(sum(len(d['questions']) for d in retained['sets']), 1)

    def test_publisher_independently_rejects_underfilled_and_duplicate_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = publication(EDITION_DATE)
            payload['sets'][0]['questions'] = payload['sets'][0]['questions'][:8]
            with self.assertRaisesRegex(ValueError, 'at least one complete set'):
                generate.publish(payload, root)
            payload = publication(EDITION_DATE)
            payload['sets'][1]['questions'][0]['prompt'] = payload['sets'][0]['questions'][0]['prompt']
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                generate.publish(payload, root)
            self.assertFalse((root / 'site/latest.json').exists())

    def test_main_incomplete_response_survives_and_later_run_tops_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = [dict(EVIDENCE[0], id=str(n)) for n in range(1, 4)]
            def response(raw):
                return io.StringIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(raw)}]}}]}))
            env = {'DAILY_GENERATION_ENABLED': 'true', 'VERTEX_ACCESS_TOKEN': 'test-only', 'RESERVED_DATE': str(EDITION_DATE)}
            with patch.dict(generate.os.environ, env), patch.object(generate, 'EDITION_DAY', str(EDITION_DATE)), patch.object(generate, 'sources', return_value=evidence):
                generate.reserve_attempt(EDITION_DATE, root)
                with patch.object(generate.urllib.request, 'urlopen', return_value=response({'sets': [topic(1, 8)]})) as api:
                    with self.assertRaisesRegex(ValueError, 'Incomplete'):
                        generate.main(root)
                    self.assertEqual(api.call_count, 1)
                candidate = root / 'state/candidates' / f'{EDITION_DATE}.json'
                original = json.loads(candidate.read_text())['sets'][0]['questions']
                self.assertEqual(len(original), 8)
                self.assertFalse((root / 'site/latest.json').exists())
                generate.reserve_attempt(EDITION_DATE, root)
                with patch.object(generate.urllib.request, 'urlopen', return_value=response({'sets': [topic(1, 12), topic(2), topic(3)]})) as api:
                    generate.main(root)
                    self.assertEqual(api.call_count, 1)
                published = json.loads((root / 'site/latest.json').read_text())
                self.assertEqual(published['sets'][0]['questions'][:8], original)
                self.assertEqual(sum(len(d['questions']) for d in published['sets']), 32)

    def test_truncated_outer_json_recovers_closed_questions_and_ignores_cut_question(self):
        complete = [question(n) for n in range(1, 6)]
        raw = '{"sets":[{"title":"Policy","questions":' + json.dumps(complete)[:-1] + ',{"source_id":"1","prompt":'
        recovered = generate.recover_complete_questions(raw)
        self.assertEqual(len(recovered['sets']), 1)
        self.assertEqual(len(recovered['sets'][0]['questions']), 5)
        self.assertEqual(recovered['sets'][0]['questions'][0]['prompt']['en'], complete[0]['prompt']['en'])

    def test_http_failure_does_not_destroy_candidate_or_block_next_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decks = generate.validate({'sets': [topic(1, 8)]}, EVIDENCE, EDITION_DATE, partial=True)
            generate.merge_candidate(decks, EVIDENCE, EDITION_DATE, root)
            candidate = root / 'state/candidates' / f'{EDITION_DATE}.json'
            before = candidate.read_bytes()
            generate.reserve_attempt(EDITION_DATE, root)
            env = {'DAILY_GENERATION_ENABLED': 'true', 'VERTEX_ACCESS_TOKEN': 'test-only', 'RESERVED_DATE': str(EDITION_DATE)}
            with patch.dict(generate.os.environ, env), patch.object(generate, 'EDITION_DAY', str(EDITION_DATE)), patch.object(generate, 'sources', return_value=EVIDENCE * 3), patch.object(generate.urllib.request, 'urlopen', side_effect=OSError('network interrupted')):
                with self.assertRaisesRegex(OSError, 'network interrupted'):
                    generate.main(root)
            self.assertEqual(candidate.read_bytes(), before)
            self.assertEqual(generate.reserve_attempt(EDITION_DATE, root), 2)
            self.assertEqual(generate.claim_generation(EDITION_DATE, root), 2)

    def test_complete_candidate_recovers_publication_without_api_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decks = generate.validate({'sets': [topic(1), topic(2), topic(3)]}, EVIDENCE, EDITION_DATE, partial=True)
            generate.merge_candidate(decks, EVIDENCE, EDITION_DATE, root)
            generate.reserve_attempt(EDITION_DATE, root)
            env = {'DAILY_GENERATION_ENABLED': 'true', 'VERTEX_ACCESS_TOKEN': 'test-only', 'RESERVED_DATE': str(EDITION_DATE)}
            with patch.dict(generate.os.environ, env), patch.object(generate, 'EDITION_DAY', str(EDITION_DATE)), patch.object(generate.urllib.request, 'urlopen') as api:
                generate.main(root)
                api.assert_not_called()
            self.assertTrue((root / 'site/latest.json').exists())

    def test_later_waves_receive_distribution_remainders(self):
        expected = {
            3: [1, 1, 1],
            4: [1, 1, 2],
            5: [1, 2, 2],
            6: [2, 2, 2],
            7: [2, 2, 3],
            8: [2, 3, 3],
        }
        for count, sizes in expected.items():
            with self.subTest(count=count):
                decks = [{'title': f'Topic {i}'} for i in range(count)]
                generate.assign_release_schedule(decks, EDITION_DATE)
                actual = [sum(deck['release_wave'] == wave for deck in decks) for wave in (1, 2, 3)]
                self.assertEqual(actual, sizes)
                self.assertEqual(
                    [deck['release_at'] for deck in decks if deck['release_wave'] == 1],
                    [f'{EDITION_DATE.isoformat()}T06:30:00+05:30'] * sizes[0],
                )
                self.assertEqual(
                    [deck['release_at'] for deck in decks if deck['release_wave'] == 2],
                    [f'{EDITION_DATE.isoformat()}T13:00:00+05:30'] * sizes[1],
                )
                self.assertEqual(
                    [deck['release_at'] for deck in decks if deck['release_wave'] == 3],
                    [f'{EDITION_DATE.isoformat()}T18:00:00+05:30'] * sizes[2],
                )

    def test_validation_keeps_three_or_more_complete_topics_and_over_60_questions(self):
        raw = {'sets': [topic(i, 15) for i in range(6)]}
        result = generate.validate(raw, EVIDENCE, EDITION_DATE)
        self.assertEqual(len(result), 6)
        self.assertEqual(sum(len(deck['questions']) for deck in result), 90)
        self.assertTrue(all(10 <= len(deck['questions']) <= 15 for deck in result))
        self.assertTrue(all(deck['release_wave'] in (1, 2, 3) for deck in result))
        self.assertEqual(result[-1]['release_wave'], 3)

    def test_validation_rejects_editions_with_fewer_than_three_valid_topics(self):
        with self.assertRaisesRegex(ValueError, 'Fewer than three distinct topics'):
            generate.validate({'sets': [topic(1), topic(2)]}, EVIDENCE, EDITION_DATE)

    def test_publication_payload_uses_v2_and_contains_all_scheduled_topics(self):
        decks = generate.validate(
            {'sets': [topic(i) for i in range(1, 5)]}, EVIDENCE, EDITION_DATE)
        generated_at = dt.datetime(2026, 10, 22, 0, tzinfo=dt.timezone.utc)
        payload = generate.build_payload(decks, EVIDENCE, EDITION_DATE, generated_at)
        self.assertEqual(payload['schema_version'], 2)
        self.assertEqual(payload['date'], EDITION_DATE.isoformat())
        self.assertEqual(len(payload['sets']), 4)
        self.assertTrue(all('release_at' in deck and 'release_wave' in deck for deck in payload['sets']))

    def test_validation_discards_topics_that_cannot_reach_ten_valid_questions(self):
        raw = {'sets': [topic(1, 9), topic(2), topic(3), topic(4)]}
        result = generate.validate(raw, EVIDENCE, EDITION_DATE)
        self.assertEqual([deck['title'] for deck in result], ['Topic 2', 'Topic 3', 'Topic 4'])
        self.assertEqual([deck['release_wave'] for deck in result], [1, 2, 3])

    def test_balance_options_distributes_correct_option_and_swaps_matching_text(self):
        raw = {'sets': [topic(1, 12)]}
        balanced = generate.balance_options(json.loads(json.dumps(raw)))
        questions = balanced['sets'][0]['questions']
        chosen = {q['correct_option_id'] for q in questions}
        self.assertGreater(len(chosen), 1)
        for index, q in enumerate(questions):
            correct_opt = next(o for o in q['options'] if o['id'] == q['correct_option_id'])
            self.assertEqual(correct_opt['text']['en'], f'Option a for {100 + index}')

    def test_read_url_and_sources_filter_size_dates_schemes_and_deduplicate(self):
        with patch.object(generate.urllib.request, 'urlopen') as mocked_open:
            mocked_open.return_value.__enter__.return_value.read.return_value = b'x' * 1_000_001
            with self.assertRaisesRegex(ValueError, 'size limit'):
                generate.read_url('https://example.org/huge.rss')

        now = dt.datetime.now(dt.timezone.utc)
        fresh_pub = email.utils.format_datetime(now - dt.timedelta(hours=2))
        stale_pub = email.utils.format_datetime(now - dt.timedelta(hours=90))
        rss = f"""<?xml version="1.0"?>
        <rss><channel>
          <item><title>&lt;b&gt;Fresh item&lt;/b&gt;</title><link>https://feeds.bbci.co.uk/news/item-1</link><pubDate>{fresh_pub}</pubDate><description>Valid description for item one.</description></item>
          <item><title>Duplicate link</title><link>https://feeds.bbci.co.uk/news/item-1</link><pubDate>{fresh_pub}</pubDate><description>Duplicate link should be skipped.</description></item>
          <item><title>Stale item</title><link>https://example.org/stale</link><pubDate>{stale_pub}</pubDate><description>Too old.</description></item>
          <item><title>Insecure link</title><link>http://example.org/insecure</link><pubDate>{fresh_pub}</pubDate><description>Non-https skipped.</description></item>
          <item><title>Undated item</title><link>https://example.org/undated</link><description>No pubDate skipped.</description></item>
        </channel></rss>""".encode('utf-8')

        calls = {'count': 0}
        def fake_read_url(url):
            calls['count'] += 1
            if calls['count'] == 1:
                raise ValueError('Source exceeds size limit')
            if calls['count'] == 2:
                return rss
            raise OSError('timeout')

        with patch.object(generate, 'read_url', side_effect=fake_read_url):
            items = generate.sources()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Fresh item')
        self.assertEqual(items[0]['url'], 'https://feeds.bbci.co.uk/news/item-1')

    def test_validate_rejects_malformed_questions_and_attributes_bbc_links(self):
        bbc_evidence = [{
            'id': '1',
            'title': 'Space agency launches climate satellite',
            'url': 'https://feeds.bbci.co.uk/news/science-1',
            'published': '2026-10-22T00:00:00+00:00',
            'text': 'The satellite measures atmospheric carbon and ocean temperatures globally.',
        }]
        good = question(1)
        good['evidence'] = 'The satellite measures atmospheric carbon and ocean temperatures globally.'
        short_quote = dict(good, evidence='too short', prompt={'en': 'Short quote question?'})
        unmatched_quote = dict(good, evidence='Completely unrelated quote that is not in the source text.', prompt={'en': 'Unmatched quote?'})
        bad_options = dict(good, options=[{'id': 'a', 'text': {'en': 'Only one'}}], prompt={'en': 'Bad options?'})
        empty_explanation = dict(good, explanation={'en': '   '}, prompt={'en': 'Empty explanation?'})
        decks = generate.validate(
            {'sets': [{'title': 'Science', 'questions': [short_quote, unmatched_quote, bad_options, empty_explanation, good]}]},
            bbc_evidence,
            EDITION_DATE,
            partial=True,
        )
        self.assertEqual(len(decks), 1)
        self.assertEqual(len(decks[0]['questions']), 1)
        self.assertIn('BBC News · https://feeds.bbci.co.uk/news/science-1', decks[0]['questions'][0]['explanation']['en'])

    def test_publish_tolerates_corrupt_existing_latest_and_history_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'site/editions').mkdir(parents=True)
            (root / 'site/latest.json').write_text('{corrupt-json')
            (root / 'site/editions' / f'{EDITION_DATE - dt.timedelta(days=1)}.json').write_text('{corrupt-archive')
            generate.publish(publication(EDITION_DATE), root)
            published = json.loads((root / 'site/latest.json').read_text())
            self.assertEqual(published['date'], str(EDITION_DATE))


if __name__ == '__main__':
    unittest.main()
