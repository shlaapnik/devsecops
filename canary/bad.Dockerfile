FROM alpine:3.22

RUN sudo apk add --no-cache curl

# hadolint ignore=DL3020
ADD app.py /app/
