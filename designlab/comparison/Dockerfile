FROM nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY style.css game.js model.js tracking.js journey.js data.js provenance.json /usr/share/nginx/html/
COPY brightness.js brightness-model.js brightness-data.js brightness-provenance.json /usr/share/nginx/html/
COPY opening.js bench.js bench.css /usr/share/nginx/html/
COPY launch.js launch-model.js launch-data.js launch-provenance.json shift.css /usr/share/nginx/html/
COPY vendor/ /usr/share/nginx/html/vendor/
COPY index.html /usr/share/nginx/html/lab.html
COPY night.html /usr/share/nginx/html/index.html
COPY night.html night.css night.js night-model.js archive-data.js archive-provenance.json learning-model.js learning-data.js learning-provenance.json /usr/share/nginx/html/
COPY night-stories.js constellation-data.js exploration-provenance.json /usr/share/nginx/html/
COPY NIGHT-SOURCES.txt /usr/share/nginx/html/
COPY world.css world-room.js world-art.js world-art-credits.md world-targets.js world-provenance.json sky-navigation.js sky-navigation-data.js sky-provenance.json /usr/share/nginx/html/
COPY art/ /usr/share/nginx/html/art/
COPY releases/night-shift.zip /usr/share/nginx/html/night-shift.zip
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
