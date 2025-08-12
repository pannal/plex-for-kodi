{# watchlist dynamic play button #}
    {# checking #}
    {% include template with name="wait" & id=2302 & visible="!String.IsEmpty(Window.Property(disable_playback)) + !String.IsEmpty(Window.Property(wl_availability_checking))" %}
    {# available multiple #}
    {% include template with name="play_plus" & id=2303 & visible="!String.IsEmpty(Window.Property(disable_playback)) + String.IsEmpty(Window.Property(wl_availability_checking)) + !String.IsEmpty(Window.Property(wl_availability_multiple))" %}
    {# available single #}
    {% include template with name="play" & id=2304 & visible="!String.IsEmpty(Window.Property(disable_playback)) + String.IsEmpty(Window.Property(wl_availability_checking)) + String.IsEmpty(Window.Property(wl_availability_multiple)) + !String.IsEmpty(Window.Property(wl_availability))" %}
    {# not available #}
    {% include template with name="upcoming" & id=2305 & visible="!String.IsEmpty(Window.Property(disable_playback)) + String.IsEmpty(Window.Property(wl_availability_checking)) + String.IsEmpty(Window.Property(wl_availability_multiple)) + String.IsEmpty(Window.Property(wl_availability))" %}
{# /watchlist dynamic play button #}