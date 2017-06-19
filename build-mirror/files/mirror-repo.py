# arguments to pass
# delorean-update:
# delorean-deps-update:
# delorean-current-update
# host_ip
import ConfigParser
import os
import StringIO
import subprocess
import re
import urllib2
import urlparse


system_repofiles_path = "/etc/yum.repos.d/"
mirror_repofiles_path = "/var/www/"

class RepoConfig(object):

    def __init__(self, repoid, netloc):
        self.repoid = repoid
        self.netloc = netloc
        self.system_repo = ConfigParser.ConfigParser()
        self.mirror_repo_config = None
        self.filename = "%s.repo" % repoid
        self.system_repofile_path = os.path.join(system_repofiles_path, self.filename)
        self.mirror_repofile_path = os.path.join(mirror_repofiles_path, self.filename)
        self.mirro_repo_urls = {}

        self.system_repo_config = self.load_config(path=self.system_repofile_path)
        self.mirror_repo_config = self.load_config(path=self.mirror_repofile_path)

        if self.mirror_repo_config is None:
            self.mirror_repo_urls, self.mirror_repo_config = self.generate_mirror_repo_config(base_config=self.system_repo_config)
            self.sync()
        else:
            self.mirror_repo_urls = self.xform_baseurl(self.mirror_repo_config)

        # Always re dump mirror config to update host ip
        self.dump_configs(mirror=True)

    def load_config(self, path=None, base_config=None, url=None):
        config = ConfigParser.ConfigParser()
        config_data = StringIO.StringIO()
        if path is not None:
            try:
                with open(path) as config_file:
                    config_data.write(config_file.read())
            except IOError:
                return None
            config_data.seek(0)
        elif base_config is not None:
            base_config.write(config_data)
            config_data.seek(0)
        elif url is not None:
            try:
                url_data = urllib2.urlopen(url)
                config_data.write(url_data.read())
                url_data.close()
            except urlparse.HTTPError:
                return None
        else:
            return None

        config.readfp(config_data)
        config_data.seek(0)
        print(config_data)
        config_data.close()

        return config

    def xform_baseurl(self, config):
        parsed_urls = {}
        for section in config.sections():
            baseurl = config.get(section, 'baseurl')
            parsed_baseurl = urlparse.urlparse(baseurl)
            mirror_repo_path = re.sub("\$basearch", "x86_64", parsed_baseurl.path)
            parsed_baseurl = parsed_baseurl._replace(path=mirror_repo_path)
            parsed_baseurl = parsed_baseurl._replace(scheme='http'
            parsed_baseurl = parsed_baseurl._replace(netloc=self.netloc)
            parsed_urls[section] = parsed_baseurl

        return parsed_urls

    def generate_mirror_repo_config(self, system_repo_config):
        mirror_repo_config = self.load_config(base_config=system_repo_config)
        mirror_repo_urls = self.xform_baseurl(system_repo_config)
        for section, parsed_url in mirror_repo_urls.items():
            baseurl = parsed_url.geturl()
            mirror_repo_config.set(section, 'baseurl', baseurl)
            mirror_repo_config.set(section, 'priority', '1')

        return mirror_repo_urls, mirror_repo_config

    def sync(self):
        for section, url in self.mirror_repo_urls.items():
            http_path = url.path
            if http_path[0] == '/':
                http_path = http_path[1:]
            path = os.path.join(mirror_repofiles_path, http_path)
            try:
                os.stat(path)
            except OSError:
                os.makedirs(path)
            repoid_arg = "--repoid=%s" % (self.repoid)
            result = subprocess.Popen(["/usr/bin/reposync", "--norepopath", "-t", "/tmp/reposync","-p", path, repoid_arg ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            print result.stdout.read()
            result.stdout.close()
            result = subprocess.Popen([ "createrepo", "--update", path ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            print result.stdout.read()
            result.stdout.close()
            inrepo_config = os.path.join(path, self.filename)
            with open(inrepo_config, "w") as inrepo_config_file:
                self.mirror_repo_config.write(inrepo_config_file)

    def update_configs(self, repo_url):
        ''' takes a repo file from URL, copies to system config, then
            mangles and update mirror config
        '''
        new_system_repo_config = self.load_config(url=repo_url)
        new_urls, new_mirror_repo_config = self.generate_mirror_repo_config(new_system_repo_config)

        for section, new_url in new_urls.items():
            new_path = new_url.path
            try:
                old_path = self.mirror_parsed_urls[section].path
            except NameError:
                old_path = None
            if new_path != old_path:
                if old_path is None:
                    os.makedirs(new_path)
                else:
                    os.renames(old_path, new_path)
        self.system_repo_config = new_system_repo_config
        self.mirror_repo_config = new_mirror_repo_config
        self.mirror_repo_urls = new_urls
        self.dump_configs(system=True, mirror=True)
        self.sync()

    def dump_configs(self, mirror=False, system=False):
        if system:
            with open(self.system_repofile_path, "w") as system_repo_config_file:
                self.system_repo_config.write(system_repo_config_file)
        if mirror:
            with open(self.mirror_repofile_path, "w") as mirror_repo_config_file:
                self.mirror_repo_config.write(mirror_repo_config_file)


try:
    host_ip = os.environ['host_ip']
    system_repofiles_path = os.environ['system_repofiles_path']
    mirror_repofiles_path = os.environ['mirror_repofiles_path']
    mirror_port = os.environ['mirror_port']
except KeyError as e:
    print("%s environment variable is mandatory" % (str(e)))
    raise

netloc = "%s:%s" % (host_ip, mirror_port)
delorean = RepoConfig('delorean', netloc)
delorean_update = os.environ.get("delorean-update", None)
delorean_deps = RepoConfig('delorean-deps', netloc)
delorean_deps_update = os.environ.get("delorean-deps-update", None)
delorean_current = RepoConfig('delorean-current', netloc)
delorean_current_update = os.environ.get("delorean-current-update", None)

if delorean_update:
    delorean.update_configs(delorean_update)
if delorean_deps_update:
    delorean.update_configs(delorean_deps_update)
if delorean_current_update:
    delorean.update_configs(delorean_current_update)
