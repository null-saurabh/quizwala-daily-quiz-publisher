import datetime as dt
import unittest

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


class DailyGenerationTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
