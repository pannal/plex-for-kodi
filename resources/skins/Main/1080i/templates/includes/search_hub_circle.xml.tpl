<itemlayout width="304" condition="String.IsEqual(Window.Property(hub.display.{{ hub_id }}),circle)">
    <control type="group">
        <posx>55</posx>
        <posy>{{ vscale(61) }}</posy>
        <control type="group">
            <posx>5</posx>
            <posy>5</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>244</width>
                <height>{{ vscale(244) }}</height>
                <texture diffuse="script.plex/masks/role.png">$INFO[ListItem.Property(thumb.fallback)]</texture>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>244</width>
                <height>{{ vscale(244) }}</height>
                <texture background="true" diffuse="script.plex/masks/role.png">$INFO[ListItem.Thumb]</texture>
                <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
            </control>
            <control type="label">
                <scroll>false</scroll>
                <posx>0</posx>
                <posy>{{ vscale(254) }}</posy>
                <width>244</width>
                <height>{{ vscale(35) }}</height>
                <font>font10</font>
                <align>center</align>
                <textcolor>FFFFFFFF</textcolor>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <posx>0</posx>
                <posy>{{ vscale(282) }}</posy>
                <width>244</width>
                <height>{{ vscale(35) }}</height>
                <font>font10</font>
                <align>center</align>
                <textcolor>FFFFFFFF</textcolor>
                <label>$INFO[ListItem.Label2]</label>
            </control>
        </control>
    </control>
</itemlayout>

<focusedlayout width="304" condition="String.IsEqual(Window.Property(hub.display.{{ hub_id }}),circle)">
    <control type="group">
        <posx>55</posx>
        <posy>{{ vscale(61) }}</posy>
        <control type="group">
            <animation effect="zoom" start="100" end="110" time="100" center="127,{{ vscale(127) }}" reversible="false">Focus</animation>
            <animation effect="zoom" start="110" end="100" time="100" center="127,{{ vscale(127) }}" reversible="false">UnFocus</animation>
            <posx>0</posx>
            <posy>0</posy>
            <control type="image">
                <visible>Control.HasFocus({{ hub_id }})</visible>
                <posx>-40</posx>
                <posy>{{ vscale(-40) }}</posy>
                <width>334</width>
                <height>{{ vscale(334) }}</height>
                <texture border="42">script.plex/buttons/role-shadow.png</texture>
            </control>
            <control type="group">
                <posx>5</posx>
                <posy>5</posy>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>244</width>
                    <height>{{ vscale(244) }}</height>
                    <texture diffuse="script.plex/masks/role.png">$INFO[ListItem.Property(thumb.fallback)]</texture>
                </control>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>244</width>
                    <height>{{ vscale(244) }}</height>
                    <texture background="true" diffuse="script.plex/masks/role.png">$INFO[ListItem.Thumb]</texture>
                    <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                </control>
                <control type="label">
                    <scroll>false</scroll>
                    <posx>0</posx>
                    <posy>{{ vscale(254) }}</posy>
                    <width>244</width>
                    <height>{{ vscale(35) }}</height>
                    <font>font10</font>
                    <align>center</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[ListItem.Label]</label>
                </control>
                <control type="label">
                    <posx>0</posx>
                    <posy>{{ vscale(282) }}</posy>
                    <width>244</width>
                    <height>{{ vscale(35) }}</height>
                    <font>font10</font>
                    <align>center</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[ListItem.Label2]</label>
                </control>
            </control>
            <control type="image">
                <visible>Control.HasFocus({{ hub_id }})</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>254</width>
                <height>{{ vscale(254) }}</height>
                <texture>script.plex/buttons/role-selected.png</texture>
            </control>
        </control>
    </control>
</focusedlayout>
