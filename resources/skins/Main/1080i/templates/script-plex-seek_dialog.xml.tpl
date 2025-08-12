{% extends "base.xml.tpl" %}
{% block headers %}
    <defaultcontrol>800</defaultcontrol>
    <zorder>100</zorder>
{% endblock %}
{% block backgroundcolor %}{% endblock %}

{% block controls %}
<control type="group" id="802">
    <visible>[!String.IsEmpty(Window.Property(show.OSD)) | Window.IsVisible(seekbar) | !String.IsEmpty(Window.Property(button.seek))] + !Window.IsVisible(osdvideosettings) + !Window.IsVisible(osdaudiosettings) + !Window.IsVisible(osdsubtitlesettings) + !Window.IsVisible(subtitlesearch) + !Window.IsActive(playerprocessinfo) + !Window.IsActive(selectdialog) + !Window.IsVisible(osdcmssettings)</visible>
    <animation effect="fade" time="200" delay="200" end="0">Hidden</animation>
    <control type="group">
        <visible>String.IsEmpty(Window.Property(is_plextuary)) + String.IsEmpty(Window.Property(settings.visible)) + [Window.IsVisible(seekbar) | Window.IsVisible(videoosd) | Player.ShowInfo]</visible>
        <animation effect="fade" start="100" end="0">Hidden</animation>
        <posx>0</posx>
        <posy>0</posy>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>1080</height>
            <texture>script.plex/player-fade.png</texture>
            <colordiffuse>FF080808</colordiffuse>
        </control>
    </control>

    <control type="group">
        <posx>0</posx>
        <posy>0</posy>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>{{ vscale(140) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>A0000000</colordiffuse>
        </control>
        <control type="image">
            <visible>String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))</visible>
            <posx>0</posx>
            <posy>{{ vscale(140) }}r</posy>
            <width>1920</width>
            <height>{{ vscale(140) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>A0000000</colordiffuse>
        </control>
    </control>

    <control type="group">
        <posx>0</posx>
        <posy>{{ vscale(40) }}</posy>
        <control type="label">
            <visible>!String.IsEmpty(Window.Property(is.show)) + String.IsEmpty(Window.Property(hide.title))</visible>
            <posx>60</posx>
            <posy>0</posy>
            <width>1720</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <scroll>true</scroll>
            <scrollspeed>15</scrollspeed>
            <label>[B]$INFO[VideoPlayer.TVShowTitle][/B]$INFO[VideoPlayer.Title, &#8226; ]$INFO[VideoPlayer.Season, &#8226; Season ]$INFO[VideoPlayer.Episode, Episode ]$INFO[Window.Property(ep.year), &#8226; ]</label>
        </control>
        <control type="label">
            <visible>!String.IsEmpty(Window.Property(is.show)) + !String.IsEmpty(Window.Property(hide.title))</visible>
            <posx>60</posx>
            <posy>0</posy>
            <width>1720</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <scroll>true</scroll>
            <scrollspeed>15</scrollspeed>
            <label>[B]$INFO[VideoPlayer.TVShowTitle][/B]$INFO[VideoPlayer.Season, &#8226; Season ]$INFO[VideoPlayer.Episode, Episode ]$INFO[Window.Property(ep.year), &#8226; ]</label>
        </control>
        <control type="label">
            <visible>String.IsEmpty(Window.Property(is.show))</visible>
            <posx>60</posx>
            <posy>0</posy>
            <width>1720</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <scroll>true</scroll>
            <scrollspeed>15</scrollspeed>
            <label>[B]$INFO[VideoPlayer.Title][/B]$INFO[VideoPlayer.Year, &#8226; ]</label>
        </control>
        <control type="label">
            <posx>1860</posx>
            <posy>0</posy>
            <width>300</width>
            <height>{{ vscale(60) }}</height>
            <font>font12</font>
            <align>right</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[System.Time]</label>
        </control>
    </control>

    <control type="group">
        <posx>0</posx>
        <posy>{{ vscale(115) }}r</posy>
        <control type="label">
            <visible>!String.IsEmpty(Window.Property(direct.play)) + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>60</posx>
            <posy>0</posy>
            <width>1000</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Player.Time($INFO[Window.Property(time.fmt)])]</label>
        </control>
        <control type="label">
            <visible>String.IsEmpty(Window.Property(direct.play)) + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>60</posx>
            <posy>0</posy>
            <width>1000</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Window.Property(time.current)]</label>
        </control>
        <control type="label">
            <visible>Player.IsTempo</visible>
            <posx>60</posx>
            <posy>{{ vscale(40) }}</posy>
            <width>1000</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>A0FFFFFF</textcolor>
            <label>$INFO[Player.PlaySpeed]x</label>
        </control>
        <control type="label">
            <visible>!String.IsEmpty(Window.Property(direct.play)) + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>1860</posx>
            <posy>0</posy>
            <width>800</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>right</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Player.TimeRemaining($INFO[Window.Property(time.fmt)])]$INFO[Window.Property(time.add)]</label>
        </control>
        <control type="label">
            <visible>String.IsEmpty(Window.Property(direct.play)) + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>1860</posx>
            <posy>0</posy>
            <width>800</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>right</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Window.Property(time.left)]</label>
        </control>
        <control type="label">
            <visible>!String.IsEmpty(Window.Property(media.show_ends)) + !String.IsEmpty(Window.Property(direct.play)) + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>1860</posx>
            <posy>{{ vscale(40) }}</posy>
            <width>800</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>right</align>
            <aligny>center</aligny>
            <textcolor>A0FFFFFF</textcolor>
            <label>$INFO[Window.Property(time.ends_label)] $INFO[Player.FinishTime($INFO[Window.Property(time.fmt.ends)])]</label>
        </control>
        <control type="label">
            <visible>!String.IsEmpty(Window.Property(media.show_ends)) + String.IsEmpty(Window.Property(direct.play)) + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>1860</posx>
            <posy>{{ vscale(40) }}</posy>
            <width>800</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>right</align>
            <aligny>center</aligny>
            <textcolor>A0FFFFFF</textcolor>
            <label>$INFO[Window.Property(time.ends_label)] $INFO[Window.Property(time.end)]</label>
        </control>
        <!--<control type="label">
            <visible>Player.Paused + String.IsEmpty(Window.Property(show.OSD))</visible>
            <animation effect="fade" time="200" delay="200" end="100">Visible</animation>
            <posx>0</posx>
            <posy>{{ vscale(20) }}</posy>
            <width>1920</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>FFCC7B19</textcolor>
            <label>[UPPERCASE]$ADDON[script.plexmod 32436][/UPPERCASE]</label>
        </control>-->
    </control>

    <control type="group">
        <posx>0</posx>
        <posy>{{ vscale(140) }}r</posy>
        <control type="image">
            <visible>String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))</visible>
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>{{ vscale(10) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>A0000000</colordiffuse>
        </control>
        <control type="image" id="206">
            <visible>!String.IsEmpty(Window.Property(show.buffer)) + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>0</posx>
            <posy>2</posy>
            <width>1</width>
            <height>{{ vscale(6) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>EE4E4842</colordiffuse>
        </control>
        <control type="image" id="201">
            <visible>String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))</visible>
            <posx>0</posx>
            <posy>2</posy>
            <width>1</width>
            <height>{{ vscale(6) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>FFAC5B00</colordiffuse>
        </control>
        <control type="image" id="200">
            <visible>[Control.HasFocus(100) | !String.IsEmpty(Window.Property(button.seek))] + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
            <posx>0</posx>
            <posy>2</posy>
            <width>1</width>
            <height>{{ vscale(6) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>FFE5A00D</colordiffuse>
        </control>
    </control>
</control>
<control type="button" id="800">
    <visible allowhiddenfocus="true">String.IsEmpty(Window.Property(show.OSD))</visible>
    <posx>0</posx>
    <posy>0</posy>
    <width>1920</width>
    <height>1080</height>
    <texturefocus>-</texturefocus>
    <texturenofocus>-</texturenofocus>
    <label> </label>
    <onclick condition="String.IsEmpty(Window.Property(button.seek)) + String.IsEmpty(Window.Property(marker.countdown)) + !String.IsEmpty(Window.Property(mouse.mode))">SetProperty(show.OSD,1)</onclick>
</control>

<!-- PPI -->
<control type="group" id="803">
    <bottom>0</bottom>
    <height>{{ vscale(350) }}</height>
    <visible>!String.IsEmpty(Window.Property(show.PPI)) + String.IsEmpty(Window.Property(settings.visible)) + String.IsEmpty(Window.Property(playlist.visible))</visible>
    <animation effect="fade" start="0" end="100" time="300">Visible</animation>
    <animation effect="fade" start="100" end="0" time="200">Hidden</animation>
    <control type="image">
        <left>10</left>
        <top>{{ vscale(-220) }}</top>
        <right>10</right>
        <height>{{ vscale(420) }}</height>
        <texture border="40">buttons/dialogbutton-nofo.png</texture>
    </control>
    <control type="grouplist">
        <left>52</left>
        <top>{{ vscale(-184) }}</top>
        <width>1786</width>
        <height>{{ vscale(350) }}</height>
        <orientation>horizontal</orientation>
        <itemgap>10</itemgap>
        <control type="grouplist">
            <left>0</left>
            <top>0</top>
            <width>793</width>
            <control type="label">
                <width>793</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>$INFO[Player.Process(videodecoder),[COLOR FFE5A00D]$LOCALIZE[31139]:[/COLOR] ]$VAR[VideoHWDecoder, (,)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo</visible>
            </control>
            <control type="label">
                <width>793</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>$INFO[Player.Process(pixformat),[COLOR FFE5A00D]$LOCALIZE[31140]:[/COLOR] ]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo</visible>
            </control>
            <control type="label">
                <width>793</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>$INFO[Player.Process(deintmethod),[COLOR FFE5A00D]$LOCALIZE[16038]:[/COLOR] ]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo</visible>
            </control>
            <control type="label">
                <width>793</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>$INFO[Player.Process(videowidth),[COLOR FFE5A00D]$LOCALIZE[38031]:[/COLOR] ,x]$INFO[Player.Process(videoheight),, px]$INFO[Player.Process(videodar),$COMMA , AR]$INFO[Player.Process(videofps),$COMMA , FPS]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo</visible>
            </control>
            <control type="textbox">
                <width>793</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <autoscroll delay="1000" time="1000" repeat="2000"></autoscroll>
                <label>[COLOR FFE5A00D]$LOCALIZE[460]:[/COLOR] $INFO[Player.Process(audiochannels),,$COMMA ]$INFO[Player.Process(audiodecoder)]$INFO[Player.Process(audiobitspersample),$COMMA , bits]$INFO[Player.Process(audiosamplerate),$COMMA , Hz]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
            </control>
            <control type="label">
                <width>793</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>$INFO[System.Memory(used.percent),[COLOR FFE5A00D]$LOCALIZE[31030]:[/COLOR] ,]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
            </control>
        </control>
        <control type="grouplist">
            <left>0</left>
            <top>0</top>
            <height>{{ vscale(350) }}</height>
            <width>993</width>
            <control type="label">
                <width>893</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>$INFO[Window.Property(ppi.Status)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + !String.IsEmpty(Window.Property(ppi.Status))</visible>
            </control>
            <control type="label">
                <width>893</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>[COLOR FFE5A00D]Mode:[/COLOR] $INFO[Window.Property(ppi.Mode)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + !String.IsEmpty(Window.Property(ppi.Mode))</visible>
            </control>
            <control type="label">
                <width>893</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>[COLOR FFE5A00D]Container:[/COLOR] $INFO[Window.Property(ppi.Container)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + !String.IsEmpty(Window.Property(ppi.Container))</visible>
            </control>
            <control type="textbox">
                <width>893</width>
                <autoscroll delay="1000" time="1000" repeat="2000"></autoscroll>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>[COLOR FFE5A00D]Video:[/COLOR] $INFO[Window.Property(ppi.Video)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + !String.IsEmpty(Window.Property(ppi.Video))</visible>
            </control>
            <control type="textbox">
                <width>893</width>
                <autoscroll delay="1000" time="1000" repeat="2000"></autoscroll>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>$INFO[Window.Property(ppi.Audio),[COLOR FFE5A00D]Audio:[/COLOR] ]$INFO[Window.Property(ppi.Subtitles),   [COLOR FFE5A00D]Subtitle:[/COLOR] ]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + [!String.IsEmpty(Window.Property(ppi.Audio)) | !String.IsEmpty(Window.Property(ppi.Subtitles))]</visible>
            </control>
            <control type="textbox">
                <width>893</width>
                <autoscroll delay="1000" time="1000" repeat="2000"></autoscroll>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>[COLOR FFE5A00D]Server:[/COLOR] $INFO[Window.Property(ppi.User)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + !String.IsEmpty(Window.Property(ppi.User))</visible>
            </control>
            <control type="label">
                <width>893</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>[COLOR FFE5A00D]Buffer:[/COLOR] $INFO[Player.CacheLevel]%$INFO[Window.Property(ppi.BufferMB), (of ~, MB]$INFO[Window.Property(ppi.ReadFactor),$COMMA Readfactor: ,x)]$INFO[Window.Property(ppi.AReadFactor),$COMMA Readfactor: ,)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + String.IsEmpty(Window.Property(ppi.Buffered))</visible>
            </control>
            <control type="label">
                <width>893</width>
                <height>{{ vscale(50) }}</height>
                <aligny>bottom</aligny>
                <label>[COLOR FFE5A00D]Buffer:[/COLOR] $INFO[Window.Property(ppi.Buffered)]% (% of Video cached)$INFO[Window.Property(ppi.BufferMB), (of ~, MB]$INFO[Window.Property(ppi.ReadFactor),$COMMA Readfactor:,x)]$INFO[Window.Property(ppi.AReadFactor),$COMMA Readfactor: ,)]</label>
                <font>font14</font>
                <shadowcolor>black</shadowcolor>
                <visible>Player.HasVideo + !String.IsEmpty(Window.Property(ppi.Buffered))</visible>
            </control>
        </control>
    </control>
    <control type="label">
        <left>52</left>
        <top>{{ vscale(120) }}</top>
        <width>1786</width>
        <height>{{ vscale(50) }}</height>
        <aligny>bottom</aligny>
        <label>$INFO[System.CpuUsage,[COLOR FFE5A00D]$LOCALIZE[13271][/COLOR] ]</label>
        <font>font14</font>
        <shadowcolor>black</shadowcolor>
    </control>
</control>
<control type="group" id="300">
    <visible>!String.IsEmpty(Window.Property(has.bif)) + !String.IsEmpty(Window.Property(bif.image)) + String.IsEmpty(Window.Property(show.chapters)) + [Control.HasFocus(100) | Control.HasFocus(501) | !String.IsEmpty(Window.Property(button.seek))] + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))] </visible>
    <animation effect="fade" time="100" delay="100" end="100">Visible</animation>
    <posx>0</posx>
    <posy>752</posy>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>324</width>
        <height>{{ vscale(184) }}</height>
        <texture>script.plex/white-square.png</texture>
        <colordiffuse>FF000000</colordiffuse>
    </control>
    <control type="image">
        <posx>2</posx>
        <posy>2</posy>
        <width>320</width>
        <height>{{ vscale(180) }}</height>
        <fadetime>10</fadetime>
        <texture>$INFO[Window.Property(bif.image)]</texture>
    </control>
</control>
<control type="group" id="801">
    <visible>!String.IsEmpty(Window.Property(show.OSD)) + !Window.IsVisible(osdvideosettings) + !Window.IsVisible(osdaudiosettings) + !Window.IsVisible(osdsubtitlesettings) + !Window.IsVisible(subtitlesearch) + !Window.IsActive(playerprocessinfo) + !Window.IsActive(selectdialog) + !Window.IsVisible(osdcmssettings)</visible>
    <animation effect="fade" time="200" delay="200" end="0">Hidden</animation>

    <control type="grouplist" id="400">
        <defaultcontrol>406</defaultcontrol>
        <hitrect x="460" y="998" w="1000" h="55" />
        <posx>360</posx>
        <posy>{{ vscale(116) }}r</posy>
        <width>1200</width>
        <height>{{ vscale(124) }}</height>
        <align>center</align>
        <onup>100</onup>
        <itemgap>-40</itemgap>
        <orientation>horizontal</orientation>
        <scrolltime tween="quadratic" easing="out">200</scrolltime>
        <usecontrolcoords>true</usecontrolcoords>
        <control type="group" id="421">
            <visible>!String.IsEmpty(Window.Property(nav.repeat))</visible>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <control type="button" id="401">
                <hitrect x="28" y="28" w="69" h="45" />
                <posx>0</posx>
                <posy>0</posy>
                <width>125</width>
                <height>{{ vscale(101) }}</height>
                <onup>100</onup>
                <onright>402</onright>
                <onleft>412</onleft>
                <ondown>501</ondown>
                <font>font12</font>
                <texturefocus>-</texturefocus>
                <texturenofocus>-</texturenofocus>
                <label> </label>
            </control>
            <control type="group">
                <visible>!Control.HasFocus(401)</visible>
                <ondown>501</ondown>
                <control type="image">
                    <visible>!Playlist.IsRepeatOne + !Playlist.IsRepeat + String.IsEmpty(Window.Property(pq.repeat))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}repeat.png</texture>
                </control>
                <control type="image">
                    <visible>Playlist.IsRepeat | !String.IsEmpty(Window.Property(pq.repeat))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture colordiffuse="FFCC7B19">{{ theme.assets.buttons.base }}repeat.png</texture>
                </control>
                <control type="image">
                    <visible>Playlist.IsRepeatOne | !String.IsEmpty(Window.Property(pq.repeat.one))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture colordiffuse="FFCC7B19">{{ theme.assets.buttons.base }}repeat-one.png</texture>
                </control>
            </control>
            <control type="group">
                <visible>Control.HasFocus(401)</visible>
                <ondown>501</ondown>
                <control type="image">
                    <visible>!Playlist.IsRepeatOne + !Playlist.IsRepeat + String.IsEmpty(Window.Property(pq.repeat))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}repeat{{ theme.assets.buttons.focusSuffix }}.png</texture>
                </control>
                <control type="image">
                    <visible>Playlist.IsRepeat | !String.IsEmpty(Window.Property(pq.repeat))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}repeat{{ theme.assets.buttons.focusSuffix }}.png</texture>
                </control>
                <control type="image">
                    <visible>Playlist.IsRepeatOne | !String.IsEmpty(Window.Property(pq.repeat.one))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}repeat-one{{ theme.assets.buttons.focusSuffix }}.png</texture>
                </control>
            </control>
        </control>

        <control type="togglebutton" id="402">
            <visible>!String.IsEmpty(Window.Property(has.playlist)) + !String.IsEmpty(Window.Property(nav.shuffle))</visible>
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}shuffle{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}shuffle.png</texturenofocus>
            <usealttexture>!String.IsEmpty(Window.Property(pq.shuffled))</usealttexture>
            <alttexturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}shuffle{{ theme.assets.buttons.focusSuffix }}.png</alttexturefocus>
            <alttexturenofocus colordiffuse="FFCC7B19">{{ theme.assets.buttons.base }}shuffle.png</alttexturenofocus>
            <label> </label>
        </control>
        <control type="button" id="422">
            <enable>false</enable>
            <visible>String.IsEmpty(Window.Property(has.playlist)) + !String.IsEmpty(Window.Property(nav.shuffle))</visible>
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}shuffle{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}shuffle.png</texturenofocus>
            <label> </label>
        </control>

        <control type="button" id="403">
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}settings{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}settings.png</texturenofocus>
            <label> </label>
        </control>


        <control type="button" id="404">
            <visible>!String.IsEmpty(Window.Property(pq.hasprev)) + !String.IsEmpty(Window.Property(nav.prevnext))</visible>
            <hitrect x="58" y="28" w="69" h="45" />
            <posx>30</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus flipx="true"{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}next{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus flipx="true"{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}next.png</texturenofocus>
            <label> </label>
        </control>
        <control type="button" id="424">
            <enable>false</enable>
            <visible>String.IsEmpty(Window.Property(pq.hasprev)) + !String.IsEmpty(Window.Property(nav.prevnext))</visible>
            <posx>30</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus flipx="true" colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}next{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus flipx="true" colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}next.png</texturenofocus>
            <label> </label>
        </control>
        <control type="button" id="405">
            <visible>!String.IsEmpty(Window.Property(nav.ffwdrwd))</visible>
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus flipx="true" colordiffuse="FFE5A00D">{{ theme.assets.buttons.base }}skip-forward{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus flipx="true"{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}skip-forward.png</texturenofocus>
            <label> </label>
        </control>

        <control type="group" id="426">
            {% if theme.buttons.zoomPlayButton %}
                <animation effect="zoom" start="100" end="124" time="100" center="63,{{ vscale(50) }}" reversible="false" condition="Control.HasFocus(406)">Conditional</animation>
                <animation effect="zoom" start="124" end="100" time="100" center="63,{{ vscale(50) }}" reversible="false" condition="!Control.HasFocus(406)">Conditional</animation>
            {% endif %}
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <control type="button" id="406">
                <hitrect x="28" y="28" w="69" h="45" />
                <posx>0</posx>
                <posy>0</posy>
                <width>125</width>
                <height>{{ vscale(101) }}</height>
                <onup>100</onup>
                <onright>407</onright>
                <onleft>405</onleft>
                <ondown>501</ondown>
                <font>font12</font>
                <texturefocus>-</texturefocus>
                <texturenofocus>-</texturenofocus>
                <label> </label>
                <onclick>PlayerControl(Play)</onclick>
            </control>
            <control type="group">
                <ondown>501</ondown>
                <visible>!Control.HasFocus(406)</visible>
                <control type="image">
                    <visible>!Player.Paused + !Player.Forwarding + !Player.Rewinding</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}pause.png</texture>
                </control>
                <control type="image">
                    <visible>Player.Paused | Player.Forwarding | Player.Rewinding</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}play.png</texture>
                </control>
            </control>
            <control type="group">
                <ondown>501</ondown>
                <visible>Control.HasFocus(406)</visible>
                <control type="image">
                    <visible>!Player.Paused + !Player.Forwarding + !Player.Rewinding</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}pause{{ theme.assets.buttons.focusSuffix }}.png</texture>
                </control>
                <control type="image">
                    <visible>Player.Paused | Player.Forwarding | Player.Rewinding</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>125</width>
                    <height>{{ vscale(101) }}</height>
                    <texture{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}play{{ theme.assets.buttons.focusSuffix }}.png</texture>
                </control>
            </control>
        </control>

        <control type="button" id="407">
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}stop{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}stop.png</texturenofocus>
            <label> </label>
        </control>
        <control type="button" id="408">
            <visible>!String.IsEmpty(Window.Property(nav.ffwdrwd))</visible>
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}skip-forward{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}skip-forward.png</texturenofocus>
            <label> </label>
        </control>
        <control type="button" id="409">
            <visible>!String.IsEmpty(Window.Property(pq.hasnext)) + !String.IsEmpty(Window.Property(nav.prevnext))</visible>
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}next{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}next.png</texturenofocus>
            <label> </label>
        </control>
        <control type="button" id="419">
            <enable>false</enable>
            <visible>String.IsEmpty(Window.Property(pq.hasnext)) + !String.IsEmpty(Window.Property(nav.prevnext))</visible>
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <ondown>501</ondown>
            <texturefocus colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}next{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}next.png</texturenofocus>
            <label> </label>
        </control>


        <control type="button" id="410">
            <visible>[!String.IsEmpty(Window.Property(pq.hasnext)) | !String.IsEmpty(Window.Property(pq.hasprev))] + !String.IsEmpty(Window.Property(nav.playlist))</visible>
            <hitrect x="58" y="28" w="69" h="45" />
            <posx>30</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}pqueue{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}pqueue.png</texturenofocus>
            <label> </label>
        </control>
        <control type="button" id="430">
            <enable>false</enable>
            <visible>String.IsEmpty(Window.Property(pq.hasnext)) + String.IsEmpty(Window.Property(pq.hasprev)) + !String.IsEmpty(Window.Property(nav.playlist))</visible>
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>30</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}pqueue{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus colordiffuse="40FFFFFF">{{ theme.assets.buttons.base }}pqueue.png</texturenofocus>
            <label> </label>
        </control>
        <control type="button" id="412">
            <visible>!String.IsEmpty(Window.Property(nav.quick_subtitles))</visible>
            <hitrect x="28" y="28" w="69" h="45" />
            <posx>0</posx>
            <posy>0</posy>
            <width>125</width>
            <height>{{ vscale(101) }}</height>
            <font>font12</font>
            <ondown>501</ondown>
            <texturefocus{% if theme.buttons.useFocusColor %} colordiffuse="{{ theme.buttons.focusColor|default("FFE5A00D") }}"{% endif %}>{{ theme.assets.buttons.base }}subtitle{{ theme.assets.buttons.focusSuffix }}.png</texturefocus>
            <texturenofocus{% if theme.buttons.useNoFocusColor %} colordiffuse="{{ theme.buttons.noFocusColor|default('99FFFFFF') }}"{% endif %}>{{ theme.assets.buttons.base }}subtitle.png</texturenofocus>
            <label> </label>
        </control>
    </control>

    <control type="group">
        <posx>0</posx>
        <posy>940</posy>
        <control type="button" id="100">
            <hitrect x="0" y="-19" w="1920" h="48" />
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>{{ vscale(10) }}</height>
            <onup>501</onup>
            <ondown>400</ondown>
            <texturefocus>-</texturefocus>
            <texturenofocus>-</texturenofocus>
        </control>
    </control>

    <control type="group" id="500">
        <animation effect="slide" time="100" start="0,0" end="0,{{ vscale(20) }}" reversible="true" condition="Control.HasFocus(501) + String.IsEmpty(Window.Property(has.chapters))">Conditional</animation>

        <!-- CHAPTERS -->
        <animation effect="slide" time="100" start="0,0" end="0,{{ vscale(-60) }}" reversible="true" condition="Control.HasFocus(501) + !String.IsEmpty(Window.Property(has.chapters)) + !String.IsEmpty(Window.Property(show.chapters))">Conditional</animation>
        <!-- /CHAPTERS -->

        <visible>String.IsEmpty(Window.Property(mouse.mode)) + String.IsEmpty(Window.Property(hide.bigseek)) + [Control.HasFocus(501) | Control.HasFocus(100)] + [!String.IsEmpty(Window.Property(show.chapters)) | String.IsEmpty(Window.Property(has.chapters))]</visible>
        <posx>-8</posx>
        <posy>917</posy>
        <control type="image">
            <posx>-200</posx>
            <posy>5</posy>
            <width>2320</width>
            <height>{{ vscale(6) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>A0000000</colordiffuse>
            <visible>String.IsEmpty(Window.Property(has.chapters))</visible>
        </control>
        <!-- CHAPTERS -->
        <control type="image">
            <posx>0</posx>
            <posy>-175</posy>
            <width>1928</width>
            <height>200</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>A0000000</colordiffuse>
            <visible>!String.IsEmpty(Window.Property(has.chapters))</visible>
        </control>
        <control type="label">
            <posx>40</posx>
            <posy>-162</posy>
            <width>auto</width>
            <height>{{ vscale(20) }}</height>
            <font>font10</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>CC606060</textcolor>
            <label>$INFO[Window.Property(chapters.label)]</label>
            <visible>!String.IsEmpty(Window.Property(has.chapters)) + !Control.HasFocus(501)</visible>
        </control>
        <control type="label">
            <posx>40</posx>
            <posy>-162</posy>
            <width>auto</width>
            <height>{{ vscale(20) }}</height>
            <font>font10</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Window.Property(chapters.label)]</label>
            <visible>!String.IsEmpty(Window.Property(has.chapters)) + Control.HasFocus(501)</visible>
        </control>
        <!-- /CHAPTERS -->
        <control type="list" id="501">
            <hitrect x="-20" y="-20" w="10" h="10" />
            <posx>0</posx>
            <posy>0</posy>
            <width>1928</width>
            <height>{{ vscale(16) }}</height>
            <ondown>100</ondown>
            <onfocus>SetProperty(hide.bigseek,)</onfocus>
            <scrolltime>200</scrolltime>
            <orientation>horizontal</orientation>
            <preloaditems>4</preloaditems>
            <!-- ITEM LAYOUT ########################################## -->
            <itemlayout width="160" condition="String.IsEmpty(Window.Property(has.chapters))">
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>16</width>
                    <height>{{ vscale(16) }}</height>
                    <texture>script.plex/indicators/seek-selection-marker.png</texture>
                    <colordiffuse>FF606060</colordiffuse>
                </control>
            </itemlayout>

            <!-- FOCUSED LAYOUT ####################################### -->
            <focusedlayout width="160" condition="String.IsEmpty(Window.Property(has.chapters))">
                <control type="image">
                    <visible>!Control.HasFocus(501)</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>16</width>
                    <height>{{ vscale(16) }}</height>
                    <texture>script.plex/indicators/seek-selection-marker.png</texture>
                    <colordiffuse>FF606060</colordiffuse>
                </control>
                <control type="image">
                    <visible>Control.HasFocus(501)</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>16</width>
                    <height>{{ vscale(16) }}</height>
                    <texture>script.plex/indicators/seek-selection-marker.png</texture>
                    <colordiffuse>FFE5A00D</colordiffuse>
                </control>
            </focusedlayout>

            <!-- ITEM LAYOUT CHAPTERS ########################################## -->
            <itemlayout width="218" condition="!String.IsEmpty(Window.Property(has.chapters))">
                <control type="group">
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>script.plex/thumb_fallbacks/movie16x9.png</texture>
                        <aspectratio>scale</aspectratio>
                        <colordiffuse>CC606060</colordiffuse>
                        <visible>!Control.HasFocus(501)</visible>
                    </control>
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>$INFO[ListItem.Thumb]</texture>
                        <aspectratio>scale</aspectratio>
                        <colordiffuse>DDAAAAAA</colordiffuse>
                        <visible>!Control.HasFocus(501)</visible>
                    </control>
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>script.plex/thumb_fallbacks/movie16x9.png</texture>
                        <aspectratio>scale</aspectratio>
                        <colordiffuse>FFAAAAAA</colordiffuse>
                        <visible>Control.HasFocus(501)</visible>
                    </control>
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>$INFO[ListItem.Thumb]</texture>
                        <aspectratio>scale</aspectratio>
                        <colordiffuse>FFAAAAAA</colordiffuse>
                        <visible>Control.HasFocus(501)</visible>
                    </control>
                    <control type="label">
                        <posx>40</posx>
                        <posy>{{ vscale(120) }}</posy>
                        <width>auto</width>
                        <height>{{ vscale(10) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>CC606060</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                        <visible>!Control.HasFocus(501)</visible>
                    </control>
                    <control type="label">
                        <posx>40</posx>
                        <posy>{{ vscale(120) }}</posy>
                        <width>auto</width>
                        <height>{{ vscale(10) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>FFAAAAAA</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                        <visible>Control.HasFocus(501)</visible>
                    </control>
                </control>
            </itemlayout>

            <!-- FOCUSED LAYOUT CHAPTERS ####################################### -->
            <focusedlayout width="218" condition="!String.IsEmpty(Window.Property(has.chapters))">
                <control type="group">
                    <animation effect="slide" time="100" start="0,0" end="0,{{ vscale(-10) }}" reversible="true">Focus</animation>
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>script.plex/thumb_fallbacks/movie16x9.png</texture>
                        <aspectratio>scale</aspectratio>
                        <colordiffuse>CC909090</colordiffuse>
                        <visible>!Control.HasFocus(501)</visible>
                    </control>
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>$INFO[ListItem.Thumb]</texture>
                        <aspectratio>scale</aspectratio>
                        <colordiffuse>FF666666</colordiffuse>
                        <visible>!Control.HasFocus(501)</visible>
                    </control>
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>script.plex/thumb_fallbacks/movie16x9.png</texture>
                        <aspectratio>scale</aspectratio>
<!--                                <colordiffuse>FF606060</colordiffuse>-->
                        <visible>Control.HasFocus(501)</visible>
                    </control>
                    <control type="image">
                        <posx>40</posx>
                        <posy>0</posy>
                        <width>178</width>
                        <height>{{ vscale(100) }}</height>
                        <texture>$INFO[ListItem.Thumb]</texture>
                        <aspectratio>scale</aspectratio>
<!--                                <colordiffuse>FFFFFFFF</colordiffuse>-->
                        <visible>Control.HasFocus(501)</visible>
                    </control>
                    <control type="label">
                        <posx>40</posx>
                        <posy>{{ vscale(120) }}</posy>
                        <width>auto</width>
                        <height>{{ vscale(10) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>FFDDDDDD</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                        <visible>!Control.HasFocus(501)</visible>
                    </control>
                    <control type="label">
                        <posx>40</posx>
                        <posy>{{ vscale(120) }}</posy>
                        <width>auto</width>
                        <height>{{ vscale(10) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
<!--                                <textcolor>FFFFFFFF</textcolor>-->
                        <label>[B]$INFO[ListItem.Label][/B]</label>
                        <visible>Control.HasFocus(501)</visible>
                    </control>
                </control>
            </focusedlayout>
        </control>
    </control>
</control>
<control type="group" id="202">
    <visible>[Control.HasFocus(100) | Control.HasFocus(501) | !String.IsEmpty(Window.Property(button.seek))] + [String.IsEmpty(Window.Property(no.osd.hide_info)) | !String.IsEmpty(Window.Property(show.OSD))]</visible>
    <posx>0</posx>
    <posy>896</posy>
    <control type="group" id="203">
        <posx>-50</posx>
        <posy>0</posy>
        <control type="image" id="204">
            <animation effect="fade" time="100" delay="100" end="100">Visible</animation>
            <posx>0</posx>
            <posy>0</posy>
            <width>101</width>
            <height>{{ vscale(39) }}</height>
            <texture>script.plex/indicators/player-selection-time_box.png</texture>
            <colordiffuse>D0000000</colordiffuse>
        </control>
        <control type="label" id="205">
            <posx>0</posx>
            <posy>0</posy>
            <width>101</width>
            <height>{{ vscale(40) }}</height>
            <font>font10</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Window.Property(time.selection)]</label>
        </control>
    </control>
    <control type="image">
        <animation effect="fade" time="100" delay="100" end="100">Visible</animation>
        <posx>-6</posx>
        <posy>{{ vscale(39) }}</posy>
        <width>15</width>
        <height>{{ vscale(7) }}</height>
        <texture>script.plex/indicators/player-selection-time_arrow.png</texture>
        <colordiffuse>D0000000</colordiffuse>
    </control>
</control>

<!-- SKIP MARKER BUTTON -->
<control type="grouplist" id="790">
    <right>30</right>
    <top>797</top>
    <width>1670</width>
    <height>143</height>
    <align>right</align>
    <orientation>horizontal</orientation>
    <control type="button" id="791">
        <visible>[!String.IsEmpty(Window.Property(show.markerSkip)) + String.IsEmpty(Window.Property(show.markerSkip_OSDOnly))] | [!String.IsEmpty(Window.Property(show.markerSkip_OSDOnly)) + !String.IsEmpty(Window.Property(show.OSD))]</visible>
        <animation effect="zoom" start="100" end="110,120" time="100" center="auto" reversible="false">Focus</animation>
        <animation effect="zoom" start="110,120" end="100" time="100" center="auto" reversible="false">UnFocus</animation>
        <animation type="Conditional" condition="String.IsEmpty(Window.Property(show.OSD)) + !Window.IsVisible(seekbar)" reversible="false">
            <effect type="slide" end="0,100" time="100" delay="100"></effect>
        </animation>
        <width min="200">auto</width>
        <height>{{ vscale(143, up=1.1) }}</height>
        <align>center</align>
        <right>0</right>
        <top>0</top>
        <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/buttons/blank-focus.png</texturefocus>
        <texturenofocus colordiffuse="99FFFFFF" border="50">script.plex/buttons/blank.png</texturenofocus>
        <textoffsetx>70</textoffsetx>
        <textcolor>FF000000</textcolor>
        <focusedcolor>FF000000</focusedcolor>
        <label>$INFO[Window.Property(skipMarkerName)]</label>
    </control>
</control>
{% endblock controls %}