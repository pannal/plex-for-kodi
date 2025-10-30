{% extends "default.xml.tpl" %}
{% block headers %}<defaultcontrol>100</defaultcontrol>{% endblock %}

{% block header %}
<control type="group" id="200">
    {% block header_animation %}<animation effect="slide" end="0,{{ vscale(-135) }}" time="200" tween="quadratic" easing="out" condition="Integer.IsGreater(Container(101).ListItem.Property(index),5) + !ControlGroup(200).HasFocus(0) + String.IsEmpty(Window.Property(content.filling))">Conditional</animation>{% endblock %}
    <defaultcontrol always="true">201</defaultcontrol>
    <posx>0</posx>
    <posy>0</posy>
    <width>1920</width>
    <height>{{ vscale(135) }}</height>
    <visible>!String.IsEmpty(Window.Property(initialized))</visible>
    {% block header_bg %}
    <control type="image">
        <animation effect="fade" start="0" end="100" time="200" tween="quadratic" easing="out" reversible="true">VisibleChange</animation>
        <visible>ControlGroup(200).HasFocus(0) + Integer.IsGreater(Container(101).ListItem.Property(index),5)</visible>
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>{{ vscale(135) }}</height>
        <texture>script.plex/white-square.png</texture>
        <colordiffuse>C0000000</colordiffuse>
    </control>
    {% endblock %}
    <control type="grouplist">
        <posx>60</posx>
        <posy>{{ vscale(47.5) }}</posy>
        <width>1000</width>
        <height>{{ vscale(40) }}</height>
        <align>left</align>
        <itemgap>60</itemgap>
        <orientation>horizontal</orientation>
        <ondown condition="String.IsEmpty(Window.Property(no.content.filtered))">50</ondown>
        <ondown condition="!String.IsEmpty(Window.Property(no.content.filtered))">600</ondown>
        <control type="group">
            <width>40</width>
            <height>{{ vscale(40) }}</height>
            <control type="button" id="201">
                <animation effect="zoom" start="100" end="144" time="100" center="20,{{ vscale(20) }}" reversible="false">Focus</animation>
                <animation effect="zoom" start="144" end="100" time="100" center="20,{{ vscale(20) }}" reversible="false">UnFocus</animation>
                <width>40</width>
                <height>{{ vscale(40) }}</height>
                <onright>202</onright>
                <ondown condition="String.IsEmpty(Window.Property(no.content.filtered))">50</ondown>
                <ondown condition="!String.IsEmpty(Window.Property(no.content.filtered))">600</ondown>
                <font>font12</font>
                <focusedcolor>FF000000</focusedcolor>
                <texturefocus colordiffuse="FFE5A00D">script.plex/buttons/home-focus.png</texturefocus>
                <texturenofocus colordiffuse="99FFFFFF">script.plex/buttons/home.png</texturenofocus>
                <label> </label>
            </control>
        </control>
        <control type="label">
            <width max="300">auto</width>
            <height>{{ vscale(40) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>[UPPERCASE]$INFO[Window.Property(screen.title)][/UPPERCASE][COLOR=gray]$INFO[Window.Property(items.count),  (,)][/COLOR]</label>
            <scroll>true</scroll>
        </control>
        <control type="group">
            <width>40</width>
            <height>{{ vscale(40) }}</height>
            <control type="button" id="202">
                <animation effect="zoom" start="100" end="144" time="100" center="20,{{ vscale(20) }}" reversible="false">Focus</animation>
                <animation effect="zoom" start="144" end="100" time="100" center="20,{{ vscale(20) }}" reversible="false">UnFocus</animation>
                <width>40</width>
                <height>{{ vscale(40) }}</height>
                <onright condition="String.IsEmpty(Window.Property(no.content.filtered))">204</onright>
                <onright condition="!String.IsEmpty(Window.Property(no.content.filtered))">600</onright>
                <onleft>201</onleft>
                <ondown condition="String.IsEmpty(Window.Property(no.content.filtered))">50</ondown>
                <ondown condition="!String.IsEmpty(Window.Property(no.content.filtered))">600</ondown>
                <font>font12</font>
                <focusedcolor>FF000000</focusedcolor>
                <texturefocus colordiffuse="FFE5A00D">script.plex/buttons/search-focus.png</texturefocus>
                <texturenofocus colordiffuse="99FFFFFF">script.plex/buttons/search.png</texturenofocus>
                <label> </label>
            </control>
        </control>
    </control>
    <control type="group">
        <visible>Player.HasAudio + String.IsEmpty(Window(10000).Property(script.plex.theme_playing))</visible>
        <posx>620</posx>
        <posy>0</posy>
        <control type="button" id="204">
            <visible>Player.HasAudio + String.IsEmpty(Window(10000).Property(script.plex.theme_playing))</visible>
            <posx>-10</posx>
            <posy>{{ vscale(38) }}</posy>
            <width>260</width>
            <height>{{ vscale(75) }}</height>
            <onleft>202</onleft>
            <ondown>50</ondown>
            <font>font12</font>
            <textcolor>FFFFFFFF</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <align>right</align>
            <aligny>center</aligny>
            <texturefocus colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texturefocus>
            <texturenofocus>-</texturenofocus>
            <textoffsetx>100</textoffsetx>
            <textoffsety>0</textoffsety>
            <label> </label>
        </control>
        <control type="image">
            <posx>0</posx>
            <posy>{{ vscale(48) }}</posy>
            <width>42</width>
            <height>{{ vscale(42) }}</height>
            <texture>$INFO[Player.Art(thumb)]</texture>
        </control>

        <control type="group">
            <visible>!Control.HasFocus(204)</visible>
            <control type="label">
                <posx>53</posx>
                <posy>{{ vscale(48) }}</posy>
                <width>187</width>
                <height>{{ vscale(20) }}</height>
                <font>font10</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <info>MusicPlayer.Artist</info>
            </control>
            <control type="label">
                <posx>53</posx>
                <posy>{{ vscale(72) }}</posy>
                <width>187</width>
                <height>{{ vscale(20) }}</height>
                <font>font10</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <info>MusicPlayer.Title</info>
            </control>
        </control>
        <control type="group">
            <visible>Control.HasFocus(204)</visible>
            <control type="label">
                <posx>53</posx>
                <posy>{{ vscale(48) }}</posy>
                <width>187</width>
                <height>{{ vscale(20) }}</height>
                <font>font10</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <info>MusicPlayer.Artist</info>
            </control>
            <control type="label">
                <posx>53</posx>
                <posy>{{ vscale(72) }}</posy>
                <width>187</width>
                <height>{{ vscale(20) }}</height>
                <font>font10</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <info>MusicPlayer.Title</info>
            </control>
        </control>

        <control type="progress">
            <description>Progressbar</description>
            <posx>0</posx>
            <posy>{{ vscale(102) }}</posy>
            <width>240</width>
            <height>{{ vscale(1) }}</height>
            <texturebg colordiffuse="9AFFFFFF">script.plex/white-square-1px.png</texturebg>
            <lefttexture>-</lefttexture>
            <midtexture colordiffuse="FFCC7B19">script.plex/white-square-1px.png</midtexture>
            <righttexture>-</righttexture>
            <overlaytexture>-</overlaytexture>
            <info>Player.Progress</info>
        </control>
    </control>
    {% block filteropts_grouplist %}
    <control type="grouplist"{% block filteropts_grouplist_attrs %} id="600"{% endblock %}>
        <visible>String.IsEmpty(Window.Property(hide.filteroptions))</visible>
        <visible>!Integer.IsGreater(Container(101).ListItem.Property(index),{% block hide_filter_from_index %}5{% endblock %}) + String.IsEmpty(Window.Property(no.content)) + !String.IsEmpty(Window.Property(initialized))</visible>
        <animation effect="slide" time="200" end="0,{{ vscale(-115) }}" tween="quadratic" easing="out" condition="Integer.IsGreater(Container(101).ListItem.Property(index),{% block hide_filter_from_index %}5{% endblock %}) + String.IsEmpty(Window.Property(content.filling))">Conditional</animation>
        {% block filteropts_animation %}
            <animation effect="fade" start="0" end="100" time="200" reversible="true">VisibleChange</animation>
        {% endblock %}
        <right>170</right>
        <posy>{{ vscale(135) }}</posy>
        <width>1000</width>
        <height>{{ vscale(65) }}</height>
        <align>right</align>
        <itemgap>30</itemgap>
        <orientation>horizontal</orientation>
        <onleft condition="String.IsEmpty(Window.Property(no.content.filtered))">304</onleft>
        <onleft condition="!String.IsEmpty(Window.Property(no.content.filtered))">200</onleft>
        <onright>151</onright>
        <ondown>101</ondown>
        <onup>200</onup>
        <control type="button" id="311">
            <enable>false</enable>
            <width max="300">auto</width>
            <height>{{ vscale(65) }}</height>
            <font>font12</font>
            <textcolor>FFFFFFFF</textcolor>
            <focusedcolor>FFFFFFFF</focusedcolor>
            <disabledcolor>FFFFFFFF</disabledcolor>
            <align>center</align>
            <aligny>center</aligny>
            <texturefocus>-</texturefocus>
            <texturenofocus>-</texturenofocus>
            <textoffsetx>0</textoffsetx>
            <textoffsety>0</textoffsety>
            <label>[UPPERCASE]$INFO[Window.Property(filter2.display)][/UPPERCASE]</label>
        </control>
        <control type="button" id="211">
            <width max="500">auto</width>
            <height>{{ vscale(65) }}</height>
            <font>font12</font>
            <textcolor>FFFFFFFF</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <align>center</align>
            <aligny>center</aligny>
            <texturefocus colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texturefocus>
            <texturenofocus>-</texturenofocus>
            <textoffsetx>20</textoffsetx>
            <textoffsety>0</textoffsety>
            <label>[UPPERCASE]$INFO[Window.Property(filter1.display)][/UPPERCASE]</label>
        </control>
        <control type="button" id="310">
            <visible>!String.IsEqual(Window.Property(media),artist)</visible>
            <enable>false</enable>
            <width max="300">auto</width>
            <height>{{ vscale(65) }}</height>
            <font>font12</font>
            <textcolor>FFFFFFFF</textcolor>
            <focusedcolor>FFFFFFFF</focusedcolor>
            <disabledcolor>FFFFFFFF</disabledcolor>
            <align>center</align>
            <aligny>center</aligny>
            <texturenofocus>-</texturenofocus>
            <texturenofocus>-</texturenofocus>
            <textoffsetx>20</textoffsetx>
            <textoffsety>0</textoffsety>
            <label>[UPPERCASE]$INFO[Window.Property(media.type)][/UPPERCASE]</label>
        </control>
        <control type="button" id="312">
            <visible>String.IsEqual(Window.Property(media),artist)</visible>
            <width max="300">auto</width>
            <height>{{ vscale(65) }}</height>
            <font>font12</font>
            <textcolor>FFFFFFFF</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <disabledcolor>FFFFFFFF</disabledcolor>
            <align>center</align>
            <aligny>center</aligny>
            <texturefocus colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texturefocus>
            <texturenofocus>-</texturenofocus>
            <textoffsetx>20</textoffsetx>
            <textoffsety>0</textoffsety>
            <label>[UPPERCASE]$INFO[Window.Property(media.type)][/UPPERCASE]</label>
        </control>
        <control type="button" id="210">
            <width max="300">auto</width>
            <height>{{ vscale(65) }}</height>
            <font>font12</font>
            <textcolor>FFFFFFFF</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <align>center</align>
            <aligny>center</aligny>
            <texturefocus colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texturefocus>
            <texturenofocus>-</texturenofocus>
            <textoffsetx>20</textoffsetx>
            <textoffsety>0</textoffsety>
            <label>[UPPERCASE]$INFO[Window.Property(sort.display)][/UPPERCASE]</label>
        </control>
    </control>
    {% endblock filteropts_grouplist %}
    <control type="label">
        <right>213</right>
        <posy>{{ vscale(35) }}</posy>
        <width>200</width>
        <height>{{ vscale(65) }}</height>
        <font>font12</font>
        <align>right</align>
        <aligny>center</aligny>
        <textcolor>FFFFFFFF</textcolor>
        <label>$INFO[System.Time]</label>
    </control>
    <control type="image">
        <posx>153r</posx>
        <posy>{{ vscale(47.5) }}</posy>
        <width>93</width>
        <height>{{ vscale(43) }}</height>
        <texture>script.plex/home/plex.png</texture>
    </control>
</control>

{% block no_content %}
<control type="group">
    <visible>!String.IsEmpty(Window.Property(no.content))</visible>
    <posx>0</posx>
    <posy>{{ vscale(465) }}</posy>
    <control type="label">
        <scroll>false</scroll>
        <posx>60</posx>
        <posy>0</posy>
        <width>1800</width>
        <height>{{ vscale(35) }}</height>
        <font>font13</font>
        <align>center</align>
        <textcolor>FFFFFFFF</textcolor>
        <label>[B]$ADDON[script.plexmod 32452][/B]</label>
    </control>
    <control type="label">
        <scroll>false</scroll>
        <posx>60</posx>
        <posy>{{ vscale(60) }}</posy>
        <width>1800</width>
        <height>{{ vscale(35) }}</height>
        <font>font13</font>
        <align>center</align>
        <textcolor>FFCCCCCC</textcolor>
        <label>$ADDON[script.plexmod 32453]</label>
    </control>
</control>

<control type="group">
    <visible>!String.IsEmpty(Window.Property(no.content.filtered))</visible>
    <posx>0</posx>
    <posy>{{ vscale(465) }}</posy>
    <control type="label">
        <scroll>false</scroll>
        <posx>60</posx>
        <posy>0</posy>
        <width>1800</width>
        <height>{{ vscale(35) }}</height>
        <font>font13</font>
        <align>center</align>
        <textcolor>FFFFFFFF</textcolor>
        <label>[B]$ADDON[script.plexmod 32454][/B]</label>
    </control>
    <control type="label">
        <scroll>false</scroll>
        <posx>60</posx>
        <posy>{{ vscale(60) }}</posy>
        <width>1800</width>
        <height>{{ vscale(35) }}</height>
        <font>font13</font>
        <align>center</align>
        <textcolor>FFCCCCCC</textcolor>
        <label>$ADDON[script.plexmod 32455]</label>
    </control>
</control>

<control type="group">
    <visible>!String.IsEmpty(Window.Property(search.dialog))</visible>
    <control type="group" >
        <visible>!String.IsEmpty(Window.Property(search.dialog.hasresults))</visible>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>1080</height>
            <texture>script.plex/home/background-fallback.png</texture>
        </control>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>1080</height>
            <texture background="true">$INFO[Window.Property(background)]</texture>
        </control>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>1080</height>
        <texture colordiffuse="99606060">script.plex/white-square.png</texture>
    </control>
</control>
{% endblock %}
{% endblock header %}