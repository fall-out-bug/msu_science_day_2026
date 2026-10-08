# A release image which keeps the proven public nginx configuration and comments API.
# The base tag is intentionally immutable within this release procedure: it is the
# currently running public image recorded in RELEASE.md.
FROM sd2026-public:scenario-comments

# Preserve the whole currently published game as a rollback-free in-site route.
# Documentation is restored at its original URL after the move; /scenario-comments
# stays in nginx configuration and continues proxying to the separate comments service.
RUN mkdir -p /usr/share/nginx/html/legacy \
 && for item in /usr/share/nginx/html/*; do \
      [ "$(basename "$item")" = legacy ] || mv "$item" /usr/share/nginx/html/legacy/; \
    done \
 && cp -a /usr/share/nginx/html/legacy/docs /usr/share/nginx/html/docs
# Keep the existing offline-download link working after the new game takes root.
RUN cp /usr/share/nginx/html/legacy/night-shift.zip /usr/share/nginx/html/night-shift.zip

# The build folder is an offline-ready, hash-manifested game release.
COPY designlab/galaxy-shift/releases/web/ /usr/share/nginx/html/
COPY designlab/galaxy-shift/releases/galaxy-shift.zip /usr/share/nginx/html/galaxy-shift.zip

# Updated design pages coexist with the unchanged historical comment anchors.
COPY designlab/comparison/docs/ /usr/share/nginx/html/docs/
COPY tools/galaxy-release/nginx.conf /etc/nginx/conf.d/default.conf
