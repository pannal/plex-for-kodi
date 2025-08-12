    <control type="grouplist">
        <visible>!String.IsEmpty(Window.Property(wl_server_availability_verbose))</visible>
        <posx>466</posx>
        <posy>{{ vscale(223) }}</posy>
        <width>1360</width>
        <height>{{ vscale(34) }}</height>
        <align>left</align>
        <itemgap>15</itemgap>
        <orientation>horizontal</orientation>
        <usecontrolcoords>true</usecontrolcoords>
        <control type="button">
            <width>auto</width>
            <height>{{ vscale(34) }}</height>
            <font>font12</font>
            <align>center</align>
            <aligny>center</aligny>
            <focusedcolor>FFFFFFFF</focusedcolor>
            <textcolor>FFFFFFFF</textcolor>
            <textoffsetx>15</textoffsetx>
            <texturefocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturefocus>
            <texturenofocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturenofocus>
            <label>[UPPERCASE]$ADDON[script.plexmod 34005][/UPPERCASE]</label>
        </control>
        <control type="label">
            <width>1160</width>
            <height>{{ vscale(34) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <scroll>true</scroll>
            <scrollspeed>10</scrollspeed>
            <label>$INFO[Window.Property(wl_server_availability_verbose)]</label>
        </control>
    </control>