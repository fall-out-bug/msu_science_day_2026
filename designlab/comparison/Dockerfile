FROM nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html style.css game.js model.js tracking.js data.js provenance.json /usr/share/nginx/html/
COPY brightness.js brightness-model.js brightness-data.js brightness-provenance.json /usr/share/nginx/html/
COPY vendor/ /usr/share/nginx/html/vendor/
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
