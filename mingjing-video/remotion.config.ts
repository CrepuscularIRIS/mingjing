import { Config } from "@remotion/cli/config";

// Render config for the MingJing explainer film.
// JPEG frames keep render fast; H.264 MP4 is the deliverable.
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// Chrome on this host is the system google-chrome; Remotion will otherwise
// download its own headless shell. Leave concurrency at the default (auto).
