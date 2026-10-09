# Build the existing release first: .venv/bin/python tools/build_release.py
FROM nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94 AS unpack
COPY dist/linux.zip /tmp/linux.zip
RUN unzip -q /tmp/linux.zip -d /site \
    && test -f /site/science-day/index.html

FROM nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
RUN rm -rf /usr/share/nginx/html/*
COPY --from=unpack /site/science-day/ /usr/share/nginx/html/
# Serve the fixed configuration directly; no writable entrypoint templates needed.
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
