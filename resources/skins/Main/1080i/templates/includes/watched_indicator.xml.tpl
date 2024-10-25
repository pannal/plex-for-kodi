{% with xoff = xoff|default(158) & yoff = yoff|default(0) & uw_size = uw_size|default(32) & wbg_w = wbg_w|default(32) & wbg_h = wbg_h|default(32) & scale_fac = indicators.scale|get(scale, "small", 1.0) %}
    {% if indicators.use_unwatched %}
    <control type="image">
        <visible>!String.IsEmpty({{ itemref|default("ListItem") }}.Property(unwatched)) + String.IsEmpty({{ itemref|default("ListItem") }}.Property(watched))</visible>
        <posx>{{ xoff - uw_size }}</posx>
        <posy>{{ uw_posy|default(0)|vscale }}</posy>
        <width>{{ uw_size }}</width>
        <height>{{ uw_size|vscale }}</height>
        <texture fallback="script.plex/indicators/{{ indicators.assets.unwatched }}">special://profile/addon_data/script.plexmod/media/{{ indicators.assets.unwatched }}</texture>
    </control>
    {% else %}
    <control type="group">
        <visible>!String.IsEmpty({{ itemref|default("ListItem") }}.Property(watched)) + String.IsEmpty({{ itemref|default("ListItem") }}.Property(unwatched.count))</visible>
        {% if indicators.use_scaling and scale_fac != 1.0 %}<animation effect="zoom" start="{{ scale_fac|mul(100)|int }}" end="{{ scale_fac|mul(100)|int }}" time="0" reversible="false" center="{{ xoff }}" condition="true">Conditional</animation>{% endif %}
        <posx>{{ xoff - wbg_w }}</posx>
        <posy>{{ yoff|vscale }}</posy>
        {% if not indicators.hide_aw_bg and not force_nowbg %}
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>{{ wbg_w }}</width>
            <height>{{ wbg_h|vscale }}</height>
            <texture>{{ wbg|default("script.plex/white-square-bl-rounded_w.png") }}</texture>
            <colordiffuse>{{ indicators.watched_bg|default("CC000000") }}</colordiffuse>
        </control>
        {% endif %}
        <control type="image">
            <posx>{{ wbg_w / 2 - 8 }}</posx>
            <posy>{{ (wbg_h / 2 - 8)|vscale }}</posy>
            <width>16</width>
            <height>{{ vscale(16) }}</height>
            <texture fallback="script.plex/indicators/{{ indicators.assets.watched }}">special://profile/addon_data/script.plexmod/media/{{ indicators.assets.watched }}</texture>
        </control>
    </control>
    {% endif %}
    {% if with_count %}
    <control type="group">
        <visible>!String.IsEmpty({{ itemref|default("ListItem") }}.Property(unwatched.count))</visible>
        {% if indicators.use_scaling and scale_fac != 1.0 %}<animation effect="zoom" start="{{ scale_fac|mul(100)|int }}" end="{{ scale_fac|mul(100)|int }}" time="0" reversible="false" center="{{ xoff }}" condition="true">Conditional</animation>{% endif %}
        {% if indicators.style == "classic" %}
        <control type="image">
            <posx>{{ xoff - wbg_w - 1 }}</posx>
            <posy>{{ yoff|vscale }}</posy>
            <width>{{ wbg_w + 1 }}</width>
            <height>{{ (wbg_h + 1)|vscale }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>FF000000</colordiffuse>
        </control>
        <control type="image">
            <posx>{{ xoff - wbg_w }}</posx>
            <posy>{{ yoff|vscale }}</posy>
            <width>{{ wbg_w }}</width>
            <height>{{ wbg_h|vscale }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>{{ indicators.unwatched_count_bg|default("FFCC7B19") }}</colordiffuse>
        </control>
        {% else %}
        <control type="image">
            <visible>String.IsEmpty({{ itemref|default("ListItem") }}.Property(unwatched.count.large))</visible>
            <posx>{{ xoff - wbg_w }}</posx>
            <posy>{{ yoff|vscale }}</posy>
            <width>{{ wbg_w }}</width>
            <height>{{ wbg_h|vscale }}</height>
            <texture>{{ wbg|default("script.plex/white-square-bl-rounded_w.png") }}</texture>
            <colordiffuse>{{ indicators.unwatched_count_bg|default("FFCC7B19") }}</colordiffuse>
        </control>
        <control type="image">
            <visible>!String.IsEmpty({{ itemref|default("ListItem") }}.Property(unwatched.count.large))</visible>
            <posx>{{ xoff - wbg_w - 16 }}</posx>
            <posy>{{ yoff|vscale }}</posy>
            <width>{{ wbg_w + 16 }}</width>
            <height>{{ wbg_h|vscale }}</height>
            <texture>{{ wbg|default("script.plex/white-square-bl-rounded_w.png") }}</texture>
            <colordiffuse>{{ indicators.unwatched_count_bg|default("FFCC7B19") }}</colordiffuse>
        </control>
        {% endif %}
        <control type="label">{# this label uses a nasty hack to get a smaller fitting font size: use a larger font, increase the label size, then zoom it down #}
            <animation effect="zoom" start="40" end="40" time="0" reversible="false" center="auto" condition="true">Conditional</animation>
            <visible>String.IsEmpty({{ itemref|default("ListItem") }}.Property(unwatched.count.large))</visible>
            <posx>{{ xoff - wbg_w - 20 }}</posx>
            <posy>{{ (yoff - 8)|vscale }}</posy>
            <width>{{ wbg_w + 40 }}</width>
            <height>{{ (wbg_h + 16)|vscale }}</height>
            <font>font32_title</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>{{ indicators.textcolor|default("FF000000") }}</textcolor>
            <label>$INFO[{{ itemref|default("ListItem") }}.Property(unwatched.count)]</label>
        </control>
        <control type="label">{# this label uses a nasty hack to get a smaller fitting font size: use a larger font, increase the label size, then zoom it down #}
            <animation effect="zoom" start="40" end="40" time="0" reversible="false" center="auto" condition="true">Conditional</animation>
            <visible>!String.IsEmpty({{ itemref|default("ListItem") }}.Property(unwatched.count.large))</visible>
            <posx>{{ xoff - wbg_w - 36 }}</posx>
            <posy>{{ (yoff - 8)|vscale }}</posy>
            <width>{{ wbg_w + 56 }}</width>
            <height>{{ (wbg_h + 16)|vscale }}</height>
            <font>font32_title</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>{{ indicators.textcolor|default("FF000000") }}</textcolor>
            <label>$INFO[{{ itemref|default("ListItem") }}.Property(unwatched.count)]</label>
        </control>
    </control>
    {% endif %}
{% endwith %}