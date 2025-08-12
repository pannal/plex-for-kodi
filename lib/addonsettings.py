# coding=utf-8
from lib.settings_util import getSetting


class AddonSettings(object):
    """
    @DynamicAttrs
    """

    _proxiedSettings = (
        ("debug", False),
        ("debug_requests", False),
        ("kodi_skip_stepping", False),
        ("auto_seek", True),
        ("auto_seek_delay", 1),
        ("dynamic_timeline_seek", False),
        ("fast_back", True),
        ("dynamic_backgrounds", True),
        ("background_art_blur_amount2", 0),
        ("background_art_opacity_amount2", 20),
        ("screensaver_quiz", False),
        ("postplay_always", False),
        ("postplay_timeout", 16),
        ("skip_intro_button_timeout", 10),
        ("skip_credits_button_timeout", 10),
        ("playlist_visit_media", False),
        ("intro_skip_early", False),
        ("show_media_ends_info", True),
        ("show_media_ends_label", True),
        ("background_colour", None),
        ("skip_intro_button_show_early_threshold2", 120),
        ("requests_timeout_connect", 5.0),
        ("requests_timeout_read", 5.0),
        ("plextv_timeout_connect", 1.0),
        ("plextv_timeout_read", 2.0),
        ("local_reach_timeout", 10),
        ("auto_skip_offset", 2.5),
        ("conn_check_timeout", 2.5),
        ("postplayCancel", True),
        ("skip_marker_timer_cancel", True),
        ("skip_marker_timer_immediate", False),
        ("low_drift_timer", True),
        ("player_show_buffer", True),
        ("buffer_wait_max", 120),
        ("buffer_insufficient_wait", 10),
        ("continue_use_thumb", True),
        ("use_bg_fallback", False),
        ("dbg_crossfade", True),
        ("subtitle_use_extended_title", True),
        ("poster_resolution_scale_perc", 100),
        ("consecutive_video_pb_wait", 0.0),
        ("retrieve_all_media_up_front", False),
        ("library_chunk_size", 240),
        ("verify_mapped_files", True),
        ("episode_no_spoiler_blur", 16),
        ("ignore_docker_v4", True),
        ("cache_home_users", True),
        ("intro_marker_max_offset", 600),
        ("hubs_rr_max", 250),
        ("max_retries1", 3),
        ("use_cert_bundle", "acme"),
        ("cache_templates", True),
        ("always_compile_templates", False),
        ("tickrate", 1.0),
        ("honor_plextv_dnsrebind", True),
        ("honor_plextv_pam", True),
        ("coreelec_resume_seek_wait", 500),
        ("background_resolution_scale_perc", 100),
        ("osd_hide_delay", 4.0),
        ("requests_cache_expiry", 168),
        ("playlist_max_size", 500),
        ("max_shutdown_wait", 5),
    )

    def __init__(self):
        # register every known setting camelCased as an attribute to this instance
        for setting, default in self._proxiedSettings:
            name_split = setting.split("_")
            setattr(self, name_split[0] + ''.join(x.capitalize() or '_' for x in name_split[1:]),
                    getSetting(setting, default))


addonSettings = AddonSettings()