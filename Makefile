# Makefile to build and deploy the load balancer stack.
# Spawned server replicas are tagged with the label below so we can clean them up.

SERVER_IMAGE  := ds-server:latest
LB_IMAGE      := ds-loadbalancer:latest
SERVER_LABEL  := role=ds-lb-server
COMPOSE       := docker compose

.PHONY: build build-server build-lb up down logs ps clean rebuild

## Build both images
build: build-server build-lb

## Build the server image on the host so the daemon can spawn replicas
build-server:
	docker build -t $(SERVER_IMAGE) ./server

## Build the load balancer image
build-lb:
	$(COMPOSE) build

## Deploy the stack (builds the server image first)
up: build-server
	$(COMPOSE) up -d

## Tear down the stack and remove any spawned server replicas
down:
	$(COMPOSE) down
	-docker ps -aq --filter "label=$(SERVER_LABEL)" | xargs -r docker rm -f

## Follow load balancer logs
logs:
	$(COMPOSE) logs -f loadbalancer

## Show stack + spawned replicas
ps:
	$(COMPOSE) ps
	docker ps --filter "label=$(SERVER_LABEL)"

## Tear down and remove built images
clean: down
	-docker rmi $(SERVER_IMAGE) $(LB_IMAGE)

## Full rebuild
rebuild: clean build up
