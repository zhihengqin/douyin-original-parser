# Douyin 32.2.6 APK: original-video API audit

Date: 2026-11-13 (Asia/Shanghai)

## Result

The locally available 32.2.6 APK did not reveal a new request path that discovers an uploaded source video from a public `aweme_id`. In particular, its 34 DEX files contain no `GetOriginVideoPlayInfo` action, no distinct `NeedOriginal` video-play action, and no route that maps a public post ID to an original media resource. This is a static audit of this APK version, not proof that no authenticated or server-only API exists.

No production code or target-media requests were changed or made during this audit.

## Evidence and interpretation

- `douyin-32.2.6/sources` contains the 476 MB `mapping.json`, not Java/smali source files. The APK contains 34 DEX files and 29,876 archive entries. Exact string scans covered all DEX files and archive entries for `GetOriginVideoPlayInfo`, `NeedOriginal`, `GetAllPlayInfo`, `originVideoResourceId`, `originalVideoInfo`, `origin_video`, `source_video`, `video/play/1/toutiao`, and `GetPlayInfo`.
- The `NeedOriginal` match resolves to `com.ss.android.ugc.aweme.audiorecord.AudioRecorderParam.needOriginalSound` and its getter/setter. It controls original sound in audio recording, not video resolution or source-file lookup. In `classes17.dex`, the `origin_video` string reference resolves to `com.ss.texturerender.VideoTextureRenderer.saveImage`, not a network request.
- `originVideoResourceId` and `originalVideoInfo` occur in client-side composer/edit models, including `com.ss.android.ugc.aweme.shortvideo.edit.VideoPublishEditModel` and `com.ss.ugc.aweme.creative.ShareToStoryModel`. The latter also carries `originAwemeId` and `isShareOriginVideo`, which describe a share-to-story/editing context. These fields could carry provenance already supplied to the composer; the APK evidence does not show them being derived from an arbitrary public post ID by a source-video fetch API.
- `com.ss.android.ugc.aweme.feed.model.playable.InteractiveVideoInfo.originalVideoInfo` is part of an interactive-feed model, not the playback model used to enumerate ordinary VOD renditions.
- The `getOriginalVid` / `getOriginalVidUrl` pair found in `com.bytedance.android.livesdkapi.depend.model.match.CollectionItem` belongs to live collection/episode data and is not a general public-aweme original lookup.
- The APK mapping includes `com.ss.ttvideoengine.fetcher.VideoInfoFetcher`, but this is the already-known playback fetcher. The existing investigation records that its callback path fetches the supplied signed URL and its fallback only changes decode/codec selection; it does not add an independent origin-resource discovery call.

## Consequence for the candidate historical action

The existing investigation notes a separate historical official action named `GetOriginVideoPlayInfo`. Its request needs an action/resource-specific signature context; the current `GetPlayInfo` token is not interchangeable. This APK contains no caller or signing path for that action, so the APK provides no grounded way to construct a valid target request from `aweme_id`. Testing guessed parameters would not be a reproducible algorithm. A usable test would first need a public source showing how a current authenticated caller obtains the required resource identity and signs that exact action; only then should the same request be checked against a known positive original and the target, with returned media independently verified.

## Audit boundary

This check does not exclude APIs that are unavailable in this APK build, hidden behind server-side authorization, or populated only for the uploader's own editing workflow. It does show that `NeedOriginal` and the `originVideoResourceId` model fields are not, by themselves, evidence of a new public-post original-video endpoint. The already tested `GetPlayInfo`/fplay, SSR, mobile-feed, and public play-dispatcher paths remain the only grounded request paths in the current investigation; none of this APK evidence supplies a missing target-resource mapping.
