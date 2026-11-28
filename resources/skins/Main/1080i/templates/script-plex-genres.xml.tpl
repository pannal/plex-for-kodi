{% extends "library.xml.tpl" %}
{% block headers %}<defaultcontrol>50</defaultcontrol>{% endblock %}

{% block content %}
<control type="group" id="50">
    <visible>!String.IsEmpty(Window.Property(initialized))</visible>
    <defaultcontrol>101</defaultcontrol>
    <posx>0</posx>
    <posy>{{ vscale(135) }}</posy>

    <control type="panel" id="101">
        <hitrect x="0" y="0" w="1920" h="945" />
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>{{ vscale(945) }}</height>
        <onup>200</onup>
        <scrolltime>200</scrolltime>
        <orientation>vertical</orientation>
        <preloaditems>2</preloaditems>

        <!-- ITEM LAYOUT ########################################## -->
        <itemlayout width="480" height="{{ vscale(290) }}">
            <control type="group">
                <posx>15</posx>
                <posy>15</posy>
                <!-- Genre art -->
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>450</width>
                    <height>{{ vscale(253) }}</height>
                    <texture background="true">$INFO[ListItem.Thumb]</texture>
                    <aspectratio>scale</aspectratio>
                </control>
                <!-- Dark overlay to make label readable -->
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>450</width>
                    <height>{{ vscale(253) }}</height>
                    <texture>script.plex/white-square.png</texture>
                    <colordiffuse>55000000</colordiffuse>
                </control>
                <!-- Genre name -->
                <control type="label">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>450</width>
                    <height>{{ vscale(253) }}</height>
                    <font>font13</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <shadowcolor>DD000000</shadowcolor>
                    <label>$INFO[ListItem.Label]</label>
                </control>
            </control>
        </itemlayout>

        <!-- FOCUSED LAYOUT ####################################### -->
        <focusedlayout width="480" height="{{ vscale(290) }}">
            <control type="group">
                <posx>15</posx>
                <posy>15</posy>
                <control type="group">
                    <animation effect="zoom" start="100" end="105" time="100" center="225,{{ vscale(126) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="105" end="100" time="100" center="225,{{ vscale(126) }}" reversible="false">UnFocus</animation>
                    <!-- Genre art -->
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>450</width>
                        <height>{{ vscale(253) }}</height>
                        <texture background="true">$INFO[ListItem.Thumb]</texture>
                        <aspectratio>scale</aspectratio>
                    </control>
                    <!-- Dark overlay -->
                    <control type="image">
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>450</width>
                        <height>{{ vscale(253) }}</height>
                        <texture>script.plex/white-square.png</texture>
                        <colordiffuse>55000000</colordiffuse>
                    </control>
                    <!-- Genre name -->
                    <control type="label">
                        <scroll>Control.HasFocus(101)</scroll>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>450</width>
                        <height>{{ vscale(253) }}</height>
                        <font>font13</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>FFFFFFFF</textcolor>
                        <shadowcolor>DD000000</shadowcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <!-- Focus ring -->
                    <control type="group">
                        <visible>Control.HasFocus(101)</visible>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>460</width>
                            <height>{{ vscale(263) }}</height>
                            <texture border="10">script.plex/home/selected.png</texture>
                        </control>
                    </control>
                </control>
            </control>
        </focusedlayout>
    </control>
</control>
{% endblock content %}
