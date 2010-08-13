;;; jetpack-test-case-support.el
;; Andrew Sutherland <asutherland@asutherland.org>
;;
;; MIT licensed.
;;
;; it's a backend mode for test-case-mode
;;   http://nschum.de/src/emacs/test-case-mode/
;;
;; it turns off all the other backends because who uses anything but jetpack?
;;
;; it assumes that your tests are in a dir like "BLAH/yourpackage/tests",
;;  that there is a "BLAH/yourpackage/package.json", and that
;;  "BLAH/jetpack-sdk" exists and is home to the jetpack sdk where it can then
;;  find a bin/activate script to source.
;;
;; I turned off the font-lock keywords because at least on my system the default
;;  coloring is quite garish (red background, yellow foreground) and I don't
;;  really have trouble picking out assertions.  Also, when you run this sucker
;;  the assertions that explode get underlined, so why do you also need
;;  blinding reminders of the things that passed?
;;
;; To hook this sucker up to your emacs setup:
;; 1) Hook up test-case-mode.el and fringe-helper.el however you want; I use
;;     elpa: http://tromey.com/elpa/
;; 2) Put this file/symlink it in a spot you've (add-to-list 'load-path
;;     "PATH")ed.  For example, I have (add-to-list 'load-path "~/.emacs.d").
;; 3) Add a (require 'jetpack-test-case-support) line to your ~/.emacs or what
;;     not after the thing that should have caused test-case-mode to get
;;     magicked.
;;
;; To make it go:
;; 1) Have test-case-mode enabled.  You can do this via M-x test-case-mode
;;     if you haven't done something fancier.
;; 2) Trigger test-case-run somehow, for example M-x test-case-run.
;;     test-case-mode has other wacky options you can use to this end.

(defun test-case-jetpack-p ()
  "Test if the current buffer is a jetpack test."
  (and (derived-mode-p 'js2-mode)
       (let ((parentdir (directory-file-name 
                         (file-name-directory (buffer-file-name)))))
         (and
          ;; in a test directory
          (equal (file-name-nondirectory parentdir) "tests")
          ;; whose parent directory has a package.json
          (file-exists-p (concat (file-name-directory parentdir)
                                 "package.json"))))))

(defun test-case-jetpack-command ()
  (let ((jetpackdir (concat (file-name-directory (buffer-file-name))
                            "../../jetpack-sdk"))
        (unittestdir (file-name-directory (buffer-file-name)))
        (testfile (file-name-nondirectory (buffer-file-name))))
    (concat "cd " jetpackdir ";"
            ". bin/activate" ";"
            "cd " unittestdir ";"
            "cfx test -F" testfile)))

;;   File "resource://wmsy-wmsy-tests/test-vs-static.js", line 56, in anonymous

(defun test-case-jetpack-failure-pattern ()
  (let ((file (regexp-quote (file-name-nondirectory (buffer-file-name)))))
    (list (concat 
           "^[.]*error: \\([^\n]+\\)\n"
           "info: Traceback (most recent call last):\n"
           "\\(?:  .+\n\\)+"
           "  File \"resource://[^/]+/\\(" file "\\)\", line \\([[:digit:]]+\\), in .+\n")
          ; name group, line group, column group, name+line, errmsg
          2 3 nil nil 1
          )))

(defvar test-case-jetpack-font-lock-keywords
  (eval-when-compile
    '()))

(defun test-case-jetpack-backend (command)
  "Jetpack unit test backend"
  (case command
    ('name "Jetpack")
    ('supported (test-case-jetpack-p))
    ('command (test-case-jetpack-command))
    ('failure-pattern (test-case-jetpack-failure-pattern))
    ('font-lock-keywords test-case-jetpack-font-lock-keywords)
    ))

(setq test-case-backends '(test-case-jetpack-backend))

(provide 'jetpack-test-case-support)
