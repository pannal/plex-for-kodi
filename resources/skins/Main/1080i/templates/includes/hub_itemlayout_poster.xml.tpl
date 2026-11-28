<!-- Poster item layout (244x361) - uses hub_id variable -->
<itemlayout width="287" condition="String.IsEqual(Window.Property(hub.display.{{ hub_id }}),poster)">
    <control type="group">
        <posx>55</posx>
        <posy>{{ vscale(72) }}</posy>
        <control type="group">
            <posx>5</posx>
            <posy>5</posy>
            <control type="group">
                <visible>!String.IsEmpty(ListItem.Property(is.end))</visible>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>244</width>
                    <height>{{ vscale(361) }}</height>
                    <texture colordiffuse="FF404040">script.plex/white-square.png</texture>
                </control>
                <control type="image">
                    <visible>String.IsEmpty(ListItem.Property(is.updating))</visible>
                    <posx>91.5</posx>
                    <posy>{{ vscale(130.5) }}</posy>
                    <width>61</width>
                    <height>{{ vscale(100) }}</height>
                    <texture colordiffuse="40000000">script.plex/indicators/chevron-white.png</texture>
                </control>
                <control type="image">
                    <visible>!String.IsEmpty(ListItem.Property(is.updating))</visible>
                    <posx>58</posx>
                    <posy>{{ vscale(116.5) }}</posy>
                    <width>128</width>
                    <height>{{ vscale(128) }}</height>
                    <texture>script.plex/home/busy.gif</texture>
                </control>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>244</width>
                <height>{{ vscale(361) }}</height>
                <texture>$INFO[ListItem.Property(thumb.fallback)]</texture>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>244</width>
                <height>{{ vscale(361) }}</height>
                <texture background="true">$INFO[ListItem.Thumb]</texture>
                <aspectratio>scale</aspectratio>
            </control>
            <control type="group">
                <visible>!String.IsEmpty(ListItem.Property(progress))</visible>
                <posx>0</posx>
                <posy>{{ vscale(351) }}</posy>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>244</width>
                    <height>{{ vscale(10) }}</height>
                    <texture>script.plex/white-square.png</texture>
                    <colordiffuse>C0000000</colordiffuse>
                </control>
                <control type="image">
                    <posx>0</posx>
                    <posy>1</posy>
                    <width>244</width>
                    <height>{{ vscale(8) }}</height>
                    <texture>$INFO[ListItem.Property(progress)]</texture>
                    <colordiffuse>FFCC7B19</colordiffuse>
                </control>
            </control>
            <control type="label">
                <scroll>false</scroll>
                <posx>0</posx>
                <posy>{{ vscale(371) }}</posy>
                <width>244</width>
                <height>{{ vscale(35) }}</height>
                <font>font10</font>
                <align>center</align>
                <textcolor>FFFFFFFF</textcolor>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <scroll>false</scroll>
                <visible>!String.IsEmpty(Window.Property(hub.text2lines.{{ hub_id }}))</visible>
                <posx>0</posx>
                <posy>{{ vscale(398) }}</posy>
                <width>244</width>
                <height>{{ vscale(35) }}</height>
                <font>font10</font>
                <align>center</align>
                <textcolor>FFFFFFFF</textcolor>
                <label>$INFO[ListItem.Label2]</label>
            </control>
            {% include "includes/watched_indicator.xml.tpl" with xoff=244 & uw_size=48 & with_count=True & scale="medium" %}
        </control>
    </control>
</itemlayout>
