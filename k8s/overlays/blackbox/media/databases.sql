\getenv prowlarr_password PROWLARR_DB_PASSWORD
\getenv radarr_password RADARR_DB_PASSWORD
\getenv sonarr_password SONARR_DB_PASSWORD
\getenv seerr_password SEERR_DB_PASSWORD

CREATE ROLE prowlarr LOGIN PASSWORD :'prowlarr_password';
CREATE ROLE radarr LOGIN PASSWORD :'radarr_password';
CREATE ROLE sonarr LOGIN PASSWORD :'sonarr_password';
CREATE ROLE seerr LOGIN PASSWORD :'seerr_password';

CREATE DATABASE prowlarr_main OWNER prowlarr;
CREATE DATABASE prowlarr_log OWNER prowlarr;
CREATE DATABASE radarr_main OWNER radarr;
CREATE DATABASE radarr_log OWNER radarr;
CREATE DATABASE sonarr_main OWNER sonarr;
CREATE DATABASE sonarr_log OWNER sonarr;
CREATE DATABASE seerr OWNER seerr;

REVOKE CONNECT ON DATABASE prowlarr_main, prowlarr_log FROM PUBLIC;
REVOKE CONNECT ON DATABASE radarr_main, radarr_log FROM PUBLIC;
REVOKE CONNECT ON DATABASE sonarr_main, sonarr_log FROM PUBLIC;
REVOKE CONNECT ON DATABASE seerr FROM PUBLIC;
