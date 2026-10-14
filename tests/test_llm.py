import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from llm import Settings, extract_journey, list_models
from test_domain import complete_journey


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.answer = complete_journey().model_dump_json()
        self.finish = "stop"
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_json(self, body):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def do_GET(self):
                self.send_json({"object": "list", "data": [{"id": "gemma-fixture", "object": "model", "created": 0, "owned_by": "local"}]})

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                case.requests.append(request)
                self.send_json({
                    "id": "fixture", "object": "chat.completion", "created": 0,
                    "model": request["model"], "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": case.answer}, "finish_reason": case.finish}],
                })

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.settings = Settings(base_url=f"http://127.0.0.1:{self.server.server_port}/v1", model="gemma-fixture")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_schema_is_sent_to_actual_http_endpoint(self):
        self.assertEqual(list_models(self.settings), ["gemma-fixture"])
        result = extract_journey("A booking excerpt.", self.settings)
        self.assertEqual(result.journey.departure_station, "Berlin Hbf")
        constraint = self.requests[0]["response_format"]
        self.assertEqual(constraint["type"], "json_schema")
        self.assertFalse(constraint["json_schema"]["schema"]["additionalProperties"])
        self.assertEqual(self.requests[0]["model"], "gemma-fixture")

    def test_prompt_only_mode_is_explicit_and_validates_json(self):
        self.answer = "```json\n" + self.answer + "\n```"
        self.settings.structured_output = False
        result = extract_journey("A booking excerpt.", self.settings)
        self.assertFalse(result.structured_output)
        self.assertNotIn("response_format", self.requests[0])

    def test_invalid_or_extra_fields_are_rejected(self):
        for answer in ("not JSON", '{"departure_station": "Berlin"}', complete_journey().model_dump_json()[:-1] + ', "extra": 1}'):
            self.answer = answer
            with self.assertRaisesRegex(ValueError, "required JSON"):
                extract_journey("A booking excerpt.", self.settings)

    def test_truncated_output_is_rejected(self):
        self.finish = "length"
        with self.assertRaisesRegex(ValueError, "token limit"):
            extract_journey("A booking excerpt.", self.settings)

    def test_missing_and_ambiguous_fields_remain_null(self):
        self.answer = complete_journey(departure_date=None, arrival_date=None, issues=["Date/year ambiguous"]).model_dump_json()
        result = extract_journey("Date is unclear.", self.settings)
        self.assertIsNone(result.journey.departure_date)
        self.assertEqual(result.journey.issues, ["Date/year ambiguous"])

    def test_remote_endpoint_is_rejected(self):
        self.settings.base_url = "https://api.openai.com/v1"
        with self.assertRaisesRegex(ValueError, "localhost"):
            extract_journey("A booking excerpt.", self.settings)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
