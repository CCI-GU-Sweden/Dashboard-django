# Manual test builds and deployments

Select project `core-omero-test` in the OpenShift console. `dashboard-django`
is both the Django **BuildConfig** and Deployment name; they are separate
resources. The BuildConfig builds `main` from the Dashboard-django GitHub
repository and writes the image to `dashboard-django:candidate`. The optional
`dashboard-build-poller` CronJob is suspended. The Django BuildConfig has no
automatic build triggers as inspected on 2026-11-18.

The Deployment is pinned to an image digest, with no automatic ImageStream
trigger. Building a new candidate does not deploy it. A Deployment's restart
restarts the image already specified in its pod template; it does not select
the newly built candidate when the Deployment is pinned to a different digest.

## Console workflow

1. Push the intended code to GitHub `main`. Confirm the correct commit and
   identify any new database migrations or grant changes. The build uses the
   repository, not uncommitted local files.
2. In **Builds → BuildConfigs**, open `dashboard-django`, choose **Actions →
   Start build**, and open the new Build. Confirm that it completes successfully
   and that its Git revision is the intended commit.
3. Inspect the completed Build and its output image, or **Builds →
   ImageStreams → dashboard-django → candidate**, and record the SHA-256 image
   digest. If another build replaces the candidate tag, select the digest for
   the specific successful Build you intend to test, not an assumed latest
   value. Do not use the separate `dashboard-modular-test` BuildConfig.
4. If the release has database changes, take and verify a test database backup,
   review and run the appropriate migrations and grants once as a separate Job.
   A build or rollout does not run the Django migrations automatically.
5. In **Workloads → Deployments → dashboard-django → YAML**, locate the `web`
   container and change only its `image` to the verified digest, using this form:

   `image-registry.openshift-image-registry.svc:5000/core-omero-test/dashboard-django@sha256:REPLACE_WITH_VERIFIED_DIGEST`

   Saving a changed pod template starts a rolling update automatically; no
   separate restart is needed. Verify the new ReplicaSet and pod image digest,
   readiness and dashboard behavior. If the desired digest is already present
   and a restart is necessary, use **Actions → Restart rollout**.
6. Once accepted in test, promote that exact tested digest to production using
   the separate reviewed process in [PRODUCTION-OPERATIONS.md](PRODUCTION-OPERATIONS.md).
   Test build and deployment operations do not change production.

As of 2026-11-18, test still runs the explicitly pinned image built by
`dashboard-modular-test` from `modular-test-2e07abd`; suspending the poller does
not change it. A manual `dashboard-django-44` build of `main` completed and is
the current candidate. Switch only when the intended candidate and migrations
have been reviewed.

## CLI equivalent

```sh
oc -n core-omero-test start-build dashboard-django --follow
oc -n core-omero-test get builds -l buildconfig=dashboard-django --sort-by=.metadata.creationTimestamp
oc -n core-omero-test get build BUILD_NAME -o jsonpath='{.spec.revision.git.commit}{" "}{.status.output.to.imageDigest}{"\n"}'
oc -n core-omero-test set image deployment/dashboard-django web=image-registry.openshift-image-registry.svc:5000/core-omero-test/dashboard-django@sha256:VERIFIED_DIGEST
oc -n core-omero-test rollout status deployment/dashboard-django
```

Replace `BUILD_NAME` and `VERIFIED_DIGEST` with the completed Build and its
digest. This explicitly updates the Deployment and causes a rollout. Avoid a
moving tag and do not infer that `oc rollout restart` selects a new candidate.
