import http from 'k6/http';
import { check, sleep } from 'k6';

// Benchmark stages adjusted for single-worker capacity and realistic thresholds
export const options = {
  stages: [
    { duration: '5s', target: 10 },  // Warm up
    { duration: '20s', target: 25 }, // Sustained load: 25 VUs (well within single-worker capacity)
    { duration: '5s', target: 0 },   // Cool down
  ],
  thresholds: {
    http_req_duration: ['p(95)<300'], // 95% of requests under 300ms
    http_req_failed: ['rate<0.01'],   // Error rate under 1%
  },
};

const BASE_URL = 'http://localhost:8000/v1/chat/completions';
const API_KEY = 'sk_live_tFFN_m8pza1qGUnaoQtHCUo3WqAt6fmXi-Qwkjz4kUA';

const payload = JSON.stringify({
  model: 'qwen2.5-coder:1.5b',
  messages: [{ role: 'user', content: 'benchmark ping' }],
  stream: false,
});

const params = {
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${API_KEY}`,
  },
};

export default function () {
  const res = http.post(BASE_URL, payload, params);

  // Validate response status & presence of rate limit headers
  check(res, {
    'status is 200': (r) => r.status === 200,
    'has rate limit remaining header': (r) => r.headers['X-Ratelimit-Remaining'] !== undefined,
  });

  // Short pause between iterations to mimic client think-time
  sleep(0.05);
}