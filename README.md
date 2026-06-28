# Customizable Load Balancer

ICS 4104: Distributed Systems — Assignment 1

A load balancer that asynchronously distributes client requests across `N`
replicated web server containers using **consistent hashing**, running inside a
Docker network. The load balancer maintains `N` healthy replicas at all times,
spawning new server containers automatically when one fails.

## Architecture

```
                 Docker network: net1
  ┌──────────────────────────────────────────────┐
  │  Server 1   Server 2   Server 3  ...           │   Async
  │     ▲          ▲          ▲                     │   requests
  │     └──────────┼──────────┘                     │  ◄────────  Client 1..N
  │          ┌─────┴──────┐                         │
  │          │ LoadBalancer│  port 5000:5000        │
  │          │   (N = 3)   │                         │
  │          └─────────────┘                         │
  └──────────────────────────────────────────────┘
```

## Project structure

```
.
├── server/                 # Task 1: minimal web server
│   ├── server.py
│   ├── Dockerfile
│   └── requirements.txt
├── loadbalancer/           # Task 3: load balancer service
│   ├── loadbalancer.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── hashing/            # Task 2: consistent hashing
│       ├── __init__.py
│       └── consistent_hash.py
├── analysis/               # Task 4: performance experiments
├── tests/
├── docker-compose.yml
├── Makefile
└── README.md
```

## Consistent hashing parameters (Task 2)

| Parameter | Value |
|-----------|-------|
| Server containers (N) | 3 |
| Total slots (#slots) | 512 |
| Virtual servers per container (K) | 9 (= log₂ 512) |
| Request hash | H(i) = i² + 2i + 17 |
| Virtual-server hash | Φ(i, j) = i² + j² + 2j + 25 |

Collisions are resolved with linear/quadratic probing.

## Load balancer endpoints (Task 3)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/rep` | List managed replicas and their count |
| POST | `/add` | Add server instances (optional preferred hostnames) |
| DELETE | `/rm` | Remove server instances |
| GET | `/<path>` | Route request to a replica via consistent hashing |

## Server endpoints (Task 1)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/home` | Returns `Hello from Server: [ID]` |
| GET | `/heartbeat` | Health check (empty 200 response) |

## Build & run

```bash
make build     # build server + load balancer images
make up        # deploy the full stack via docker-compose
make down      # tear down
make logs      # follow load balancer logs
```

## Analysis (Task 4)

See `analysis/` for the experiment scripts and `README` observations for:
- A-1: load distribution over 10,000 requests at N=3 (bar chart)
- A-2: scalability as N goes 2→6 (line chart)
- A-3: failure recovery demonstration
- A-4: effect of modified hash functions

## Design choices & assumptions

_TODO: document during implementation._

## Testing

_TODO._

## Performance analysis

_TODO._
