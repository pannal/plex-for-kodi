{% extends "base.xml.tpl" %}
{% block headers %}
<defaultcontrol>60</defaultcontrol>
{% endblock headers %}
{% block backgroundcolor %}{% endblock %}
{% block controls %}
<control type="image">
    <posx>0</posx>
    <posy>0</posy>
    <width>1920</width>
    <height>1080</height>
    <texture colordiffuse="99606060" border="10">script.plex/white-square.png</texture>
</control>
<control type="group">
    <posx>585</posx>
    <posy>{{ vperc(vscale(749)) }}</posy>
    <control type="image">
        <posx>-40</posx>
        <posy>{{ vscale(-40) }}</posy>
        <width>830</width>
        <height>{{ vscale(749) }}</height>
        <texture border="42">script.plex/drop-shadow.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>750</width>
        <height>{{ vscale(80) }}</height>
        <texture border="10">script.plex/white-square-top-rounded.png</texture>
        <colordiffuse>F21F1F1F</colordiffuse>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>{{ vscale(80) }}</posy>
        <width>750</width>
        <height>{{ vscale(627) }}</height>
        <texture flipy="true" border="10">script.plex/white-square-top-rounded.png</texture>
        <colordiffuse>D3111111</colordiffuse>
    </control>
    <control type="label">
        <posx>20</posx>
        <posy>0</posy>
        <width>710</width>
        <height>{{ vscale(80) }}</height>
        <font>font12</font>
        <align>left</align>
        <aligny>center</aligny>
        <textcolor>FFFFFFFF</textcolor>
        <label>[B][UPPERCASE]$ADDON[script.plexmod 35053][/UPPERCASE][/B]</label>
    </control>
    <control type="label">
        <posx>20</posx>
        <posy>{{ vscale(80) }}</posy>
        <width>710</width>
        <height>{{ vscale(50) }}</height>
        <font>font10</font>
        <align>left</align>
        <aligny>center</aligny>
        <textcolor>FFBBBBBB</textcolor>
        <label>$ADDON[script.plexmod 35087]</label>
    </control>
    <control type="list" id="100">
        <posx>0</posx>
        <posy>{{ vscale(130) }}</posy>
        <width>750</width>
        <height>{{ vscale(372) }}</height>
        <scrolltime>200</scrolltime>
        <orientation>vertical</orientation>
        <ondown>50</ondown>
        <itemlayout height="{{ vscale(100) }}">
            <control type="image">
                <posx>20</posx>
                <posy>{{ vscale(20) }}</posy>
                <width>60</width>
                <height>60</height>
                <texture>$INFO[ListItem.Icon]</texture>
                <aspectratio>keep</aspectratio>
            </control>
            <control type="label">
                <posx>100</posx>
                <posy>0</posy>
                <width>530</width>
                <height>{{ vscale(100) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <scroll>true</scroll>
                <scrollspeed>15</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <visible>!String.IsEmpty(ListItem.Property(access_unknown))</visible>
                <posx>100</posx>
                <posy>{{ vscale(55) }}</posy>
                <width>530</width>
                <height>{{ vscale(35) }}</height>
                <font>font10</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFBBBBBB</textcolor>
                <label>$ADDON[script.plexmod 35077]</label>
            </control>
            <control type="image">
                <posx>670</posx>
                <posy>{{ vscale(28) }}</posy>
                <width>44</width>
                <height>44</height>
                <texture colordiffuse="EE000000" border="10">script.plex/settings/checkbox.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(selected))</visible>
                <posx>670</posx>
                <posy>{{ vscale(28) }}</posy>
                <width>44</width>
                <height>44</height>
                <texture>script.plex/settings/checkmark.png</texture>
            </control>
        </itemlayout>
        <focusedlayout height="{{ vscale(100) }}">
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>750</width>
                <height>{{ vscale(100) }}</height>
                <texture colordiffuse="FFE5A00D">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>20</posx>
                <posy>{{ vscale(20) }}</posy>
                <width>60</width>
                <height>60</height>
                <texture>$INFO[ListItem.Icon]</texture>
                <aspectratio>keep</aspectratio>
            </control>
            <control type="label">
                <posx>100</posx>
                <posy>0</posy>
                <width>530</width>
                <height>{{ vscale(100) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <scroll>true</scroll>
                <scrollspeed>15</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <visible>!String.IsEmpty(ListItem.Property(access_unknown))</visible>
                <posx>100</posx>
                <posy>{{ vscale(55) }}</posy>
                <width>530</width>
                <height>{{ vscale(35) }}</height>
                <font>font10</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FF222222</textcolor>
                <label>$ADDON[script.plexmod 35077]</label>
            </control>
            <control type="image">
                <posx>670</posx>
                <posy>{{ vscale(28) }}</posy>
                <width>44</width>
                <height>44</height>
                <texture colordiffuse="EE000000" border="10">script.plex/settings/checkbox.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(selected))</visible>
                <posx>670</posx>
                <posy>{{ vscale(28) }}</posy>
                <width>44</width>
                <height>44</height>
                <texture>script.plex/settings/checkmark.png</texture>
            </control>
        </focusedlayout>
    </control>
    <control type="label">
        <visible>!String.IsEmpty(Window.Property(empty))</visible>
        <posx>0</posx>
        <posy>{{ vscale(130) }}</posy>
        <width>750</width>
        <height>{{ vscale(372) }}</height>
        <font>font12</font>
        <align>center</align>
        <aligny>center</aligny>
        <textcolor>FFBBBBBB</textcolor>
        <label>$ADDON[script.plexmod 35078]</label>
    </control>
    <control type="grouplist" id="50">
        <defaultcontrol always="true">60</defaultcontrol>
        <posx>0</posx>
        <posy>{{ vscale(552) }}</posy>
        <width>750</width>
        <height>{{ vscale(155) }}</height>
        <align>center</align>
        <itemgap>-50</itemgap>
        <orientation>horizontal</orientation>
        <scrolltime>0</scrolltime>
        <usecontrolcoords>true</usecontrolcoords>
        <onup>100</onup>
        <control type="button" id="60">
            <animation effect="zoom" start="100" end="110,120" time="100" center="auto" reversible="false">Focus</animation>
            <animation effect="zoom" start="110,120" end="100" time="100" center="auto" reversible="false">UnFocus</animation>
            <posx>0</posx>
            <posy>0</posy>
            <width min="240">auto</width>
            <height>{{ vscale(143) }}</height>
            <font>font10</font>
            <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/buttons/blank-focus.png</texturefocus>
            <texturenofocus colordiffuse="99FFFFFF" border="50">script.plex/buttons/blank.png</texturenofocus>
            <align>center</align>
            <textoffsetx>0</textoffsetx>
            <textcolor>FF000000</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <label>$ADDON[script.plexmod 32997]</label>
        </control>
        <control type="button" id="61">
            <animation effect="zoom" start="100" end="110,120" time="100" center="auto" reversible="false">Focus</animation>
            <animation effect="zoom" start="110,120" end="100" time="100" center="auto" reversible="false">UnFocus</animation>
            <posx>0</posx>
            <posy>0</posy>
            <width min="240">auto</width>
            <height>{{ vscale(143) }}</height>
            <font>font10</font>
            <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/buttons/blank-focus.png</texturefocus>
            <texturenofocus colordiffuse="99FFFFFF" border="50">script.plex/buttons/blank.png</texturenofocus>
            <align>center</align>
            <textoffsetx>0</textoffsetx>
            <textcolor>FF000000</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <label>$ADDON[script.plexmod 35073]</label>
        </control>
    </control>
</control>
{% endblock controls %}
