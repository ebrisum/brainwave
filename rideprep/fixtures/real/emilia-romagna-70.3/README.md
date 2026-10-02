# IRONMAN 70.3 Italy Emilia-Romagna — bike course

`im703_emilia_romagna_bike_2023.gpx`: the 2023 bike course as exported from Openrunner (supplied by the user for
testing; course geometry © the organiser). One 90 km loop from the Cervia promenade through the Saline di Cervia, the
Romagna countryside and Forlimpopoli to Bertinoro and back. The file is sparse (737 points), so the build snaps it to
the road network first.

```
gpx2course build fixtures/real/emilia-romagna-70.3/im703_emilia_romagna_bike_2023.gpx --name "IRONMAN 70.3 Emilia-Romagna" \
    --event-start 2026-09-20T08:45:00+02:00 --tier full --targets web,unreal
gpx2course game <courseId> --kit emilia-romagna --render "saline:9.6:cockpit,bertinoro:46.7:drone:back"
```
